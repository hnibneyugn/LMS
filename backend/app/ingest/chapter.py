from dataclasses import dataclass


@dataclass
class Chapter:
    title: str
    content_md: str
    order_index: int

    def to_dict(self) -> dict:
        """Shape stored in user_files.draft_outline (jsonb)."""
        return {
            "title": self.title,
            "content_md": self.content_md,
            "order_index": self.order_index,
        }
