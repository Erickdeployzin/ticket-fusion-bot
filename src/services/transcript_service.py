"""Serviço de geração de transcripts profissionais em HTML via API do Discord."""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.core.logger import get_logger
from src.database.schemas import GuildSettingsSchema, TicketSchema

logger = get_logger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


@dataclass(frozen=True)
class TranscriptAttachmentItem:
    filename: str
    url: str
    size_kb: float


@dataclass(frozen=True)
class TranscriptEmbedItem:
    title: str | None
    description: str | None


@dataclass(frozen=True)
class TranscriptMessageItem:
    author_name: str
    avatar_url: str
    is_bot: bool
    timestamp: str
    content: str
    embeds: list[TranscriptEmbedItem]
    attachments: list[TranscriptAttachmentItem]


class TranscriptService:
    """Coleta histórico completo via API do Discord e renderiza arquivo HTML seguro."""

    def __init__(self) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(_TEMPLATES_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
            enable_async=True,
        )

    @staticmethod
    def _format_dt(dt: datetime | None, tz_name: str) -> str:
        if dt is None:
            return "Em andamento"
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            tz = ZoneInfo("UTC")
        return dt.astimezone(tz).strftime("%d/%m/%Y às %H:%M:%S (%Z)")

    async def generate_html_file(
        self,
        channel: discord.TextChannel,
        ticket: TicketSchema,
        settings: GuildSettingsSchema,
        *,
        message_limit: int = 500,
    ) -> discord.File:
        """Busca mensagens pela API do Discord e retorna um discord.File HTML pronto para envio."""
        collected: list[TranscriptMessageItem] = []

        async for msg in channel.history(limit=message_limit, oldest_first=True):
            embeds = [
                TranscriptEmbedItem(title=emb.title, description=emb.description)
                for emb in msg.embeds
                if emb.title or emb.description
            ]
            attachments = [
                TranscriptAttachmentItem(
                    filename=att.filename,
                    url=att.url,
                    size_kb=round(att.size / 1024, 1),
                )
                for att in msg.attachments
            ]
            collected.append(
                TranscriptMessageItem(
                    author_name=f"{msg.author.display_name} ({msg.author.id})",
                    avatar_url=msg.author.display_avatar.url,
                    is_bot=msg.author.bot,
                    timestamp=self._format_dt(msg.created_at, settings.timezone),
                    content=msg.clean_content,
                    embeds=embeds,
                    attachments=attachments,
                )
            )

        guild = channel.guild
        opener = guild.get_member(ticket.opener_id)
        opener_display = (
            f"{opener.display_name} ({ticket.opener_id})"
            if opener
            else f"ID: {ticket.opener_id}"
        )

        if ticket.claimed_by_id:
            staff = guild.get_member(ticket.claimed_by_id)
            staff_display = (
                f"{staff.display_name} ({ticket.claimed_by_id})"
                if staff
                else f"ID: {ticket.claimed_by_id}"
            )
        else:
            staff_display = "Não assumido"

        template = self._env.get_template("transcript.html")
        html_content = await template.render_async(
            guild_name=guild.name,
            channel_name=channel.name,
            ticket=ticket,
            opener_display=opener_display,
            staff_display=staff_display,
            opened_at_str=self._format_dt(ticket.created_at, settings.timezone),
            closed_at_str=self._format_dt(ticket.closed_at, settings.timezone),
            generated_at_str=self._format_dt(datetime.now(UTC), settings.timezone),
            brand_footer=settings.brand_footer,
            messages=collected,
        )

        buffer = io.BytesIO(html_content.encode("utf-8"))
        filename = f"transcript-{ticket.ticket_number:04d}-{channel.name}.html"
        logger.info(
            "Transcript HTML gerado para ticket #%04d (%d mensagens).",
            ticket.ticket_number,
            len(collected),
        )
        return discord.File(fp=buffer, filename=filename)