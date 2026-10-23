"""Text shown in Discord: vocabulary cards, lists and the help message."""

from ..storage import Record, SaveResult, Stats
from ..timefmt import format_taipei

HELP_MARKER = "**拾物單字簿 SnapVocab**"

HELP_TEXT = HELP_MARKER + """
在這個頻道上傳生活物品的照片，我會回覆中文、英文、日文單字卡，並存進**你自己**的紀錄。

**如何使用**
1. 上傳照片。**一次只能辨識一張圖片**：同一則訊息附上多張時，只處理第一張，其餘會被忽略。
2. 一張照片請只放一個主要物品。照片裡有多個物品時，我會列出候選按鈕讓上傳者選擇。
3. 候選裡沒有你要的，按「其他（自己輸入）」輸入物品的中文名稱即可。

**指令**
`!最近`　顯示你最近 10 筆查詢
`!單字 紀錄ID`　取回指定紀錄的完整單字卡（不會重新辨識）
`!統計`　你的成功查詢次數與不重複單字數
`!匯出`　傳送只含你自己紀錄的 Excel 單字簿（.xlsx）

**支援內容**：PNG、JPEG、WebP、GIF，8 MB 以內的日常物品照片。每人每分鐘最多查詢 3 次。

**資料範圍**：紀錄依 Discord 帳號分開保存，只有你能用指令查看自己的紀錄。原圖不會保存。
**隱私提醒**：Excel 會以附件傳到這個頻道。資料依帳號分開，不代表附件只有你看得到，有頻道權限的人仍可能下載。這不是私人訊息。
**限制**：辨識與翻譯由 AI 產生，可能有誤，請自行核對。"""


FIRST_USE_TIP = "-# 👋 第一次使用？一次只能辨識一張圖片；完整說明請看頻道置頂訊息。"

CHANNEL_TOPIC = (
    "上傳一張生活物品照片，查中英日單字｜一次只能辨識一張｜"
    "指令：!最近 !單字 !統計 !匯出｜完整說明請看置頂訊息"
)


def format_card(record: Record, result: SaveResult | None = None) -> str:
    c = record.card
    lines = [
        f"## {c.zh_name}　`#{record.id}`",
        f"🇬🇧 **{c.en_word}**（{c.en_pos}）",
        f"> {c.en_example}",
        f"> {c.en_example_zh}",
        f"🇯🇵 **{c.ja_word}**（{c.ja_kana} / {c.ja_romaji}）",
        f"> {c.ja_example}",
        f"> {c.ja_example_zh}",
    ]
    if c.note:
        lines.append(f"📝 {c.note}")
    lines.append(f"🕒 {format_taipei(record.created_at)}")
    if result is not None and result.times_seen > 1:
        lines.append(
            f"📌 這是你第 {result.times_seen} 次查到這個單字（首次：{format_taipei(result.first_seen_at)}）"
        )
    lines.append("-# AI 辨識與翻譯可能有誤，請自行核對。")
    return "\n".join(lines)


def format_recent(records: list[Record]) -> str:
    lines = ["**最近的查詢**（`!單字 紀錄ID` 可看完整單字卡）"]
    for r in records:
        c = r.card
        lines.append(f"`#{r.id}`　{c.zh_name}　/　{c.en_word}　/　{c.ja_word}")
    return "\n".join(lines)


def format_stats(stats: Stats) -> str:
    return f"📊 成功查詢次數：**{stats.total}**\n不重複單字數：**{stats.distinct}**"
