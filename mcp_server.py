import asyncio
import json
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from services import db, library

db.init_db()

app = Server("pdf2md-library")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_folders",
            description="List all folders in the library",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="list_papers",
            description="List papers in a folder, or root-level papers if no folder_id given",
            inputSchema={
                "type": "object",
                "properties": {
                    "folder_id": {
                        "type": "integer",
                        "description": "Folder ID; omit for root papers",
                    },
                },
            },
        ),
        Tool(
            name="list_all_papers",
            description="List every paper in the library regardless of folder",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="search_papers",
            description="Search papers by title (case-insensitive)",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
        Tool(
            name="search_content",
            description="Full-text search across all paper markdown content",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
        Tool(
            name="get_paper",
            description="Get metadata for a specific paper by ID",
            inputSchema={
                "type": "object",
                "properties": {"paper_id": {"type": "integer"}},
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="get_paper_content",
            description="Get the full markdown content of a single paper by ID",
            inputSchema={
                "type": "object",
                "properties": {"paper_id": {"type": "integer"}},
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="get_all_paper_content",
            description="Get the full markdown content of every paper in the library",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_comments",
            description="Get all notes/comments for a paper",
            inputSchema={
                "type": "object",
                "properties": {"paper_id": {"type": "integer"}},
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="add_comment",
            description="Add a note/comment to a paper",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {"type": "integer"},
                    "content": {"type": "string"},
                },
                "required": ["paper_id", "content"],
            },
        ),
        Tool(
            name="get_paper_tags",
            description="Get tags assigned to a paper",
            inputSchema={
                "type": "object",
                "properties": {"paper_id": {"type": "integer"}},
                "required": ["paper_id"],
            },
        ),
        Tool(
            name="list_all_tags",
            description="List all tags defined in the library",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


def _read_md(paper) -> str:
    try:
        return Path(paper["md_path"]).read_text(encoding="utf-8")
    except OSError:
        return ""


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    def rows_to_json(rows) -> str:
        return json.dumps([dict(r) for r in rows], indent=2)

    match name:
        case "list_folders":
            result = rows_to_json(library.get_all_folders())

        case "list_papers":
            folder_id = arguments.get("folder_id")
            result = rows_to_json(library.get_papers_in_folder(folder_id))

        case "list_all_papers":
            all_papers = list(library.get_papers_in_folder(None))
            for folder in library.get_all_folders():
                all_papers.extend(library.get_papers_in_folder(folder["id"]))
            result = rows_to_json(all_papers)

        case "search_papers":
            result = rows_to_json(library.search_papers_by_title(arguments["query"]))

        case "search_content":
            result = rows_to_json(library.search_papers_by_content(arguments["query"]))

        case "get_paper":
            paper = library.get_paper(arguments["paper_id"])
            result = json.dumps(dict(paper)) if paper else "Paper not found"

        case "get_paper_content":
            paper = library.get_paper(arguments["paper_id"])
            if not paper:
                result = "Paper not found"
            else:
                content = _read_md(paper)
                result = content if content else "Markdown file not found"

        case "get_all_paper_content":
            all_papers = list(library.get_papers_in_folder(None))
            for folder in library.get_all_folders():
                all_papers.extend(library.get_papers_in_folder(folder["id"]))
            parts = [
                f"# {p['title']} (id={p['id']})\n\n{_read_md(p)}"
                for p in all_papers
            ]
            result = "\n\n---\n\n".join(parts) if parts else "No papers found"

        case "get_comments":
            result = rows_to_json(library.get_comments(arguments["paper_id"]))

        case "add_comment":
            library.add_comment(arguments["paper_id"], arguments["content"])
            result = "Comment added"

        case "get_paper_tags":
            result = rows_to_json(library.get_paper_tags(arguments["paper_id"]))

        case "list_all_tags":
            result = rows_to_json(library.get_all_tags())

        case _:
            result = f"Unknown tool: {name}"

    return [TextContent(type="text", text=result)]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
