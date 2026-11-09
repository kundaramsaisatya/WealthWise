def normalize_account_holder(value):
    """Normalize explicit account-holder labels for conservative matching."""
    return " ".join(str(value or "").strip().casefold().split())


def select_account_holder_documents(documents):
    """
    Select documents for one account holder.

    If owner identity is present, select documents matching the most recently
    reported identified owner. If no document identifies an owner, retain only
    the newest single document instead of merging unknown owners.
    """
    if not isinstance(documents, list):
        raise ValueError("Documents must be a list.")

    identified = [
        item for item in documents
        if isinstance(item, dict)
        and isinstance(item.get("account_holder"), str)
        and item["account_holder"].strip()
    ]

    if not documents:
        return [], None

    if identified:
        latest = max(
            identified,
            key=lambda item: (
                item.get("report_date") or "",
                item.get("saved_at") or "",
            ),
        )
        active = normalize_account_holder(latest["account_holder"])
        selected = [
            item for item in documents
            if normalize_account_holder(item.get("account_holder")) == active
        ]
        return selected, latest["account_holder"].strip()

    newest = max(
        documents,
        key=lambda item: (
            item.get("report_date") or "",
            item.get("saved_at") or "",
        ),
    )
    return [newest], None
