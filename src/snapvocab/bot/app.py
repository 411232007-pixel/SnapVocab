"""Discord Gateway bot: listens to one channel, handles photo uploads and the ! commands."""

import asyncio
import logging
from io import BytesIO
from urllib.parse import urlparse

import discord
from discord.ext import commands

from ..config import (
    ALLOWED_ATTACHMENT_HOSTS, CHOICE_TIMEOUT, EXPORT_COOLDOWN, EXPORT_MAX_FILES,
    IMAGE_RATE_LIMIT, MAX_IMAGE_BYTES, Settings,
)
from ..export import ExportError, build_exports, export_filename
from ..services.images import ImageError, prepare_image
from ..services.ratelimit import RateLimiter
from ..storage import Database
from ..vision import ClaudeVision, VisionError
from ..models import OBJECT_NAME_RULE, ValidationError, validate_object_name
from .formatting import FIRST_USE_TIP, HELP_MARKER, HELP_TEXT, format_card, format_recent, format_stats

log = logging.getLogger(__name__)

NO_MENTIONS = discord.AllowedMentions.none()
GENERIC_ERROR = "發生未預期的錯誤，請稍後再試。"
NO_RECORDS = "你還沒有任何紀錄。上傳一張物品照片開始吧！"
_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")
_DEFAULT_FILE_LIMIT = 10 * 1024 * 1024


class ManualNameModal(discord.ui.Modal, title="輸入物品名稱"):
    name = discord.ui.TextInput(label="物品的中文名稱", placeholder="例如：電風扇", max_length=30)

    def __init__(self, view: "ChoiceView"):
        super().__init__()
        self.choice_view = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        view = self.choice_view
        try:
            name = validate_object_name(str(self.name.value))
        except ValidationError:
            await interaction.response.send_message(OBJECT_NAME_RULE + "請再按一次「其他」重新輸入。", ephemeral=True)
            return
        if view._done:
            await interaction.response.send_message("這個選擇已經處理過了。", ephemeral=True)
            return
        view._done = True
        view.stop()
        await interaction.response.edit_message(content=f"🔍 正在整理「{name}」…", view=None)
        text = await view.bot.lookup_text(str(interaction.user.id), name)
        await interaction.edit_original_response(content=text, allowed_mentions=NO_MENTIONS)


class ChoiceView(discord.ui.View):
    """Candidate buttons plus a manual-entry button; only the original uploader may press them."""

    def __init__(self, bot: "SnapVocabBot", owner_id: int, names: list[str]):
        super().__init__(timeout=CHOICE_TIMEOUT)
        self.bot, self.owner_id = bot, owner_id
        self.message: discord.Message | None = None
        self._done = False
        for name in names:
            button = discord.ui.Button(label=name[:80], style=discord.ButtonStyle.primary)
            button.callback = self._make_callback(name)
            self.add_item(button)
        other = discord.ui.Button(label="其他（自己輸入）", style=discord.ButtonStyle.success)
        other.callback = self._other
        self.add_item(other)
        cancel = discord.ui.Button(label="取消", style=discord.ButtonStyle.secondary)
        cancel.callback = self._cancel
        self.add_item(cancel)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("只有上傳照片的人可以選擇。", ephemeral=True)
            return False
        if self._done:
            await interaction.response.send_message("這個選擇已經處理過了。", ephemeral=True)
            return False
        return True

    def _make_callback(self, name: str):
        async def callback(interaction: discord.Interaction) -> None:
            self._done = True
            self.stop()
            await interaction.response.edit_message(content=f"🔍 正在整理「{name}」…", view=None)
            text = await self.bot.lookup_text(str(interaction.user.id), name)
            await interaction.edit_original_response(content=text, allowed_mentions=NO_MENTIONS)
        return callback

    async def _other(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ManualNameModal(self))

    async def _cancel(self, interaction: discord.Interaction) -> None:
        self._done = True
        self.stop()
        await interaction.response.edit_message(content="已取消。", view=None)

    async def on_timeout(self) -> None:
        if self._done or self.message is None:
            return
        try:
            await self.message.edit(content="選擇逾時，請重新上傳照片。", view=None)
        except discord.HTTPException:
            pass


class SnapVocabBot(commands.Bot):
    def __init__(self, settings: Settings, db: Database, vision: ClaudeVision):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents, help_command=None,
                         allowed_mentions=NO_MENTIONS)
        self.settings, self.db, self.vision = settings, db, vision
        self.image_limiter = RateLimiter(*IMAGE_RATE_LIMIT)
        self.export_limiter = RateLimiter(1, EXPORT_COOLDOWN)
        self._register_commands()

    async def on_ready(self) -> None:
        log.info("logged in as %s, watching channel %s", self.user, self.settings.channel_id)
        try:
            await self.ensure_pinned_help()
        except Exception:
            log.exception("could not set up the pinned help message")

    async def ensure_pinned_help(self) -> None:
        """Keep one pinned help message by this bot in the channel, creating or updating it."""
        channel = self.get_channel(self.settings.channel_id) or await self.fetch_channel(self.settings.channel_id)
        async for pinned in channel.pins(limit=50):
            if pinned.author.id == self.user.id and pinned.content.startswith(HELP_MARKER):
                if pinned.content != HELP_TEXT:
                    await pinned.edit(content=HELP_TEXT)
                    log.info("updated pinned help message")
                return
        message = await channel.send(HELP_TEXT, allowed_mentions=NO_MENTIONS)
        try:
            await message.pin()
            log.info("posted and pinned help message")
        except discord.Forbidden:
            log.warning("help message posted but could not be pinned: grant the bot "
                        "'Pin Messages' (or 'Manage Messages') in this channel, or pin it by hand")

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.channel.id != self.settings.channel_id:
            return
        if message.attachments:
            await self.handle_upload(message)
            return
        await self.process_commands(message)

    # ---- photo upload -------------------------------------------------

    async def handle_upload(self, message: discord.Message) -> None:
        att = message.attachments[0]
        name = att.filename.lower()
        is_image = (att.content_type or "").startswith("image/") or name.endswith(_IMAGE_EXTENSIONS)
        if not is_image:
            await message.reply("這不是圖片，請上傳 PNG、JPEG、WebP 或 GIF 照片。",
                                allowed_mentions=NO_MENTIONS, mention_author=False)
            return
        if att.size > MAX_IMAGE_BYTES:
            await message.reply("圖片超過 8 MB，請縮小後重傳。",
                                allowed_mentions=NO_MENTIONS, mention_author=False)
            return
        if urlparse(att.url).hostname not in ALLOWED_ATTACHMENT_HOSTS:
            log.warning("rejected attachment host: %s", urlparse(att.url).hostname)
            await message.reply("無法處理這個附件來源。",
                                allowed_mentions=NO_MENTIONS, mention_author=False)
            return
        user_id = str(message.author.id)
        wait = self.image_limiter.try_acquire(user_id)
        if wait:
            await message.reply(f"查詢太頻繁了，請約 {int(wait) + 1} 秒後再試。",
                                allowed_mentions=NO_MENTIONS, mention_author=False)
            return

        extra = len(message.attachments) - 1
        notice = f"🔍 處理中…（一次只辨識一張，其餘 {extra} 張已忽略）" if extra else "🔍 處理中…"
        status = await message.reply(notice, allowed_mentions=NO_MENTIONS, mention_author=False)
        try:
            data = await att.read()
            jpeg = await asyncio.to_thread(prepare_image, data)
            ident = await self.vision.identify(jpeg)
            candidates = [c for c in ident.candidates if c.confidence != "low"]
            if not candidates:
                view = ChoiceView(self, message.author.id, [])
                await status.edit(content="看不出這是什麼物品。可以換一張更清楚的照片，或按下方按鈕自己輸入物品名稱：",
                                  view=view)
                view.message = status
            elif ident.single_clear_target and candidates[0].confidence == "high":
                await status.edit(content=await self.lookup_text(user_id, candidates[0].zh_name),
                                  allowed_mentions=NO_MENTIONS)
            else:
                view = ChoiceView(self, message.author.id, [c.zh_name for c in candidates[:4]])
                await status.edit(content="照片裡可能有以下物品，請上傳者選擇要查哪一個（都不是的話可以自己輸入）：", view=view)
                view.message = status
        except (ImageError, VisionError) as exc:
            await status.edit(content=f"❌ {exc}")
        except Exception:
            log.exception("upload handling failed")
            await status.edit(content=f"❌ {GENERIC_ERROR}")

    async def lookup_text(self, user_id: str, zh_name: str) -> str:
        """Generate, validate and save a card for a confirmed object; return the reply text."""
        try:
            first_use = (await asyncio.to_thread(self.db.stats, user_id)).total == 0
            card = await self.vision.generate(zh_name)
            result = await asyncio.to_thread(self.db.add_record, user_id, card)
        except VisionError as exc:
            return f"❌ {exc}"
        except Exception:
            log.exception("lookup failed")
            return f"❌ {GENERIC_ERROR}"
        text = format_card(result.record, result)
        return text + "\n" + FIRST_USE_TIP if first_use else text

    # ---- commands -----------------------------------------------------

    def _register_commands(self) -> None:
        @self.command(name="最近")
        async def recent_cmd(ctx: commands.Context) -> None:
            records = await asyncio.to_thread(self.db.recent, str(ctx.author.id), 10)
            await ctx.reply(format_recent(records) if records else NO_RECORDS, mention_author=False)

        @self.command(name="單字")
        async def word_cmd(ctx: commands.Context, record_id: str = "") -> None:
            if not record_id.lstrip("#").isdigit():
                await ctx.reply("用法：`!單字 紀錄ID`，例如 `!單字 12`。", mention_author=False)
                return
            rid = int(record_id.lstrip("#"))
            record = await asyncio.to_thread(self.db.get, str(ctx.author.id), rid)
            if record is None:
                await ctx.reply(f"找不到你的紀錄 #{rid}。", mention_author=False)
                return
            await ctx.reply(format_card(record), mention_author=False)

        @self.command(name="統計")
        async def stats_cmd(ctx: commands.Context) -> None:
            stats = await asyncio.to_thread(self.db.stats, str(ctx.author.id))
            await ctx.reply(format_stats(stats) if stats.total else NO_RECORDS, mention_author=False)

        @self.command(name="匯出")
        async def export_cmd(ctx: commands.Context) -> None:
            user_id = str(ctx.author.id)
            records = await asyncio.to_thread(self.db.all_records, user_id)
            if not records:
                await ctx.reply(NO_RECORDS, mention_author=False)
                return
            wait = self.export_limiter.try_acquire(user_id)
            if wait:
                await ctx.reply(f"匯出太頻繁了，請約 {int(wait) + 1} 秒後再試。", mention_author=False)
                return
            limit = ctx.guild.filesize_limit if ctx.guild else _DEFAULT_FILE_LIMIT
            try:
                files = await asyncio.to_thread(build_exports, records, int(limit * 0.9), EXPORT_MAX_FILES)
            except ExportError as exc:
                await ctx.reply(f"❌ {exc}", mention_author=False)
                return
            attachments = [
                discord.File(BytesIO(data), filename=export_filename(user_id, i, len(files)))
                for i, data in enumerate(files)
            ]
            await ctx.reply(
                "📎 這是你目前的單字簿快照（只含你自己的紀錄）。附件在頻道內，有權限的人仍可下載。",
                files=attachments, mention_author=False,
            )

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
            await ctx.reply("指令格式不正確，請看頻道置頂的說明。", mention_author=False)
            return
        log.error("command error in %s: %r", ctx.command, error)
        await ctx.reply(GENERIC_ERROR, mention_author=False)
