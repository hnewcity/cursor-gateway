"""Conservative checks for custom input before dispatch to the client's executor."""


def custom_input_error(args: dict, format_: dict | None) -> str | None:
    if format_ is None:
        return None
    value = args.get("input")
    if not isinstance(value, str):
        return "The custom tool requires its complete input in an input string."
    if set(args) != {"input"}:
        return "The custom tool accepts exactly one argument: input."
    # Recognize the declared Codex patch envelope, not the tool's name. Other
    # Lark/regex grammars remain the client's responsibility; do not pretend to
    # provide general constrained decoding or rewrite a proposed patch.
    grammar = format_.get("definition", "")
    if not (
        format_.get("type") == "grammar"
        and format_.get("syntax") == "lark"
        and 'begin_patch: "*** Begin Patch" LF' in grammar
        and 'end_patch: "*** End Patch" LF?' in grammar
    ):
        return None
    lines = value.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines or lines[0] != "*** Begin Patch":
        return "The first line must be exactly '*** Begin Patch', with no trailing stars."
    if lines[-1] != "*** End Patch":
        return "The last line must be exactly '*** End Patch', with no trailing stars."
    if len(lines) < 3:
        return "A patch requires at least one Add File, Update File, or Delete File hunk."
    if not lines[1].startswith(("*** Add File: ", "*** Update File: ", "*** Delete File: ")):
        return "The patch must start with an Add File, Update File, or Delete File hunk."
    return None
