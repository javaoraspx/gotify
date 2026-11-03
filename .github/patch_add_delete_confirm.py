"""Gotify Android local modification for a side-by-side, Chinese-localized build.

Run from the repository root:
    python3 .github/patch_add_delete_confirm.py

Patches, in place:
  1. app/src/main/kotlin/com/github/gotify/messages/MessagesActivity.kt
     - the per-item delete button and swipe-to-delete now ask for confirmation first
  2. app/src/main/res/values/strings.xml
     - adds the delete_message_confirm string
  3. app/build.gradle.kts
     - applicationIdSuffix ".confirm" so it can be installed next to the official app
     - app_name -> "Gotify CN"
  4. app/src/main/AndroidManifest.xml
     - two hardcoded English labels now use string resources (translatable)

The Chinese resources live in app/src/main/res/values-zh/ and are committed as files,
they do not need patching.

The script is idempotent and fails loudly if the upstream code no longer matches.
"""

import pathlib
import re
import sys

ACTIVITY = "app/src/main/kotlin/com/github/gotify/messages/MessagesActivity.kt"
STRINGS = "app/src/main/res/values/strings.xml"
GRADLE = "app/build.gradle.kts"
MANIFEST = "app/src/main/AndroidManifest.xml"

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

APPLICATION_ID_LINE = '        applicationId = "com.github.gotify"'
APP_NAME_LINE = '        resValue("string", "app_name", "Gotify")'


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


def patch_gradle(text: str) -> str:
    if 'applicationIdSuffix = ".confirm"' in text:
        print("build.gradle.kts: already patched, skipping")
        return text
    if APPLICATION_ID_LINE not in text:
        sys.exit("build.gradle.kts: applicationId line not found - upstream changed")

    # Side-by-side install next to the official app (different package id).
    text = text.replace(
        APPLICATION_ID_LINE,
        APPLICATION_ID_LINE + '\n        applicationIdSuffix = ".confirm"',
        1,
    )
    if APP_NAME_LINE in text:
        text = text.replace(
            APP_NAME_LINE,
            '        resValue("string", "app_name", "Gotify CN")',
            1,
        )
    return text


def patch_manifest(text: str) -> str:
    if 'android:label="@string/login"' in text:
        print("AndroidManifest.xml: already patched, skipping")
        return text
    for old, new in (
        ('android:label="Login"', 'android:label="@string/login"'),
        ('android:label="Push message"', 'android:label="@string/push_message"'),
    ):
        if old not in text:
            sys.exit(f"AndroidManifest.xml: {old} not found - upstream changed")
        text = text.replace(old, new, 1)
    return text


def apply(path: str, fn) -> None:
    file = pathlib.Path(path)
    before = file.read_text(encoding="utf-8")
    after = fn(before)
    if after != before:
        file.write_text(after, encoding="utf-8")
        print(f"{path}: patched")


def main() -> None:
    apply(ACTIVITY, patch_activity)
    apply(STRINGS, patch_strings)
    apply(GRADLE, patch_gradle)
    apply(MANIFEST, patch_manifest)
    print("done")


if __name__ == "__main__":
    main()
