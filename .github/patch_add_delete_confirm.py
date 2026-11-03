"""Add a confirmation dialog before deleting a message in the Gotify Android app.

Run from the repository root, e.g.:
    python3 .github/patch_add_delete_confirm.py

It patches two files in place:
  1. app/src/main/kotlin/com/github/gotify/messages/MessagesActivity.kt
     - the per-item delete button and the swipe-to-delete gesture now both ask first
  2. app/src/main/res/values/strings.xml
     - adds the delete_message_confirm string

The script is idempotent and fails loudly if the upstream code no longer matches.
"""

import pathlib
import re
import sys

ACTIVITY = "app/src/main/kotlin/com/github/gotify/messages/MessagesActivity.kt"
STRINGS = "app/src/main/res/values/strings.xml"

OLD_SIGNATURE = "private fun scheduleDeletion(message: Message) {"
NEW_SIGNATURE = "private fun scheduleDeletion(message: Message, onCancel: () -> Unit = {}) {"

DELETE_RE = re.compile(
    r"^(?P<i>[ \t]*)private fun scheduleDeletion\(message: Message\) \{\n"
    r".*?"
    r"^(?P=i)\}[ \t]*$",
    re.S | re.M,
)

SWIPE_CALL_RE = re.compile(r"^(?P<i>[ \t]*)scheduleDeletion\(message\.message\)[ \t]*$", re.M)
SWIPE_POS_RE = re.compile(r"^(?P<i>[ \t]*)val position = viewHolder\.adapterPosition[ \t]*$", re.M)

DIALOG_BODY = [
    "    // Ask before deleting a single message (this also covers swipe-to-delete).",
    "    MaterialAlertDialogBuilder(this)",
    "        .setTitle(R.string.delete_message)",
    "        .setMessage(R.string.delete_message_confirm)",
    "        .setPositiveButton(R.string.yes) { _, _ -> performDeletion(message) }",
    "        .setNegativeButton(R.string.no) { _, _ -> onCancel() }",
    "        .setOnCancelListener { onCancel() }",
    "        .show()",
]


def patch_activity(text: str) -> str:
    if "private fun performDeletion(message: Message)" in text:
        print("MessagesActivity.kt: already patched, skipping")
        return text

    match = DELETE_RE.search(text)
    if match is None:
        sys.exit("MessagesActivity.kt: scheduleDeletion() not found - upstream changed")

    indent = match.group("i")
    old_block = match.group(0)

    dialog_fn = "\n".join([indent + NEW_SIGNATURE] + [indent + line for line in DIALOG_BODY] + [indent + "}"])
    perform_fn = old_block.replace(OLD_SIGNATURE, "private fun performDeletion(message: Message) {", 1)

    text = text[: match.start()] + dialog_fn + "\n\n" + perform_fn + text[match.end():]

    # Swipe: keep the row visible again when the user cancels the dialog.
    if len(SWIPE_CALL_RE.findall(text)) != 1:
        sys.exit("MessagesActivity.kt: expected exactly one scheduleDeletion(message.message) call")
    text = SWIPE_CALL_RE.sub(
        lambda m: m.group("i") + "scheduleDeletion(message.message) { adapter.notifyItemChanged(position) }",
        text,
        count=1,
    )
    text = SWIPE_POS_RE.sub(
        lambda m: m.group("i") + "val position = viewHolder.adapterPosition\n"
        + m.group("i") + "if (position == RecyclerView.NO_POSITION) return",
        text,
        count=1,
    )
    return text


def patch_strings(text: str) -> str:
    if "delete_message_confirm" in text:
        print("strings.xml: already patched, skipping")
        return text
    anchor = '    <string name="delete_message">Delete message</string>'
    if anchor not in text:
        sys.exit("strings.xml: delete_message anchor not found - upstream changed")
    added = anchor + '\n    <string name="delete_message_confirm">Do you really want to delete this message?</string>'
    return text.replace(anchor, added, 1)


def main() -> None:
    activity = pathlib.Path(ACTIVITY)
    strings = pathlib.Path(STRINGS)

    before = activity.read_text(encoding="utf-8")
    after = patch_activity(before)
    if after != before:
        activity.write_text(after, encoding="utf-8")
        print("MessagesActivity.kt: patched")

    before = strings.read_text(encoding="utf-8")
    after = patch_strings(before)
    if after != before:
        strings.write_text(after, encoding="utf-8")
        print("strings.xml: patched")

    print("done")


if __name__ == "__main__":
    main()
