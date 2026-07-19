class ExtractError(Exception):
    """Extraction failed for a reason the user can act on.

    The message is Vietnamese and is surfaced directly as
    user_files.error_message, so it must stay user-facing prose.
    """
