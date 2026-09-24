"""A request-local, memory-only store for Cursor's generated web-search documents."""

import re

from .proto import agent_pb2 as pb
from .protocol import ProtocolError


class SearchScratch:
    def __init__(self, max_bytes: int):
        self.files: dict[str, bytes] = {}
        self.size = 0
        self.max_bytes = max_bytes

    def handle(self, execution: pb.ExecServerMessage) -> pb.AgentClientMessage:
        reply = pb.AgentClientMessage()
        response = reply.exec_client_message
        response.id, response.exec_id = execution.id, execution.exec_id
        if execution.WhichOneof("message") == "write_args":
            args = execution.write_args
            if not re.fullmatch(r"agent-tools/[A-Za-z0-9_-]+\.txt", args.path):
                response.write_result.error.CopyFrom(
                    pb.WriteError(
                        path=args.path,
                        error="Only ephemeral search documents are writable here. "
                        "Use the caller's tools to edit workspace files.",
                    )
                )
                return reply
            data = args.file_bytes or args.file_text.encode()
            size = self.size + len(data) - len(self.files.get(args.path, b""))
            if size > self.max_bytes or (args.path not in self.files and len(self.files) >= 128):
                raise ProtocolError("web search document buffer limit exceeded")
            self.files[args.path], self.size = data, size
            text = data.decode("utf-8", errors="replace")
            response.write_result.success.CopyFrom(
                pb.WriteSuccess(
                    path=args.path,
                    lines_created=len(text.splitlines()),
                    file_size=len(data),
                    file_content_after_write=text if args.return_file_content_after_write else "",
                )
            )
        else:
            args = execution.read_args
            data = self.files.get(args.path)
            if data is None:
                response.read_result.error.CopyFrom(
                    pb.ReadError(
                        path=args.path,
                        error="This path is not a search document. "
                        "Use the caller's tools to read workspace files.",
                    )
                )
                return reply
            lines = data.decode("utf-8", errors="replace").splitlines(keepends=True)
            offset = max(0, args.offset - 1)
            end = offset + args.limit if args.limit > 0 else len(lines)
            response.read_result.success.CopyFrom(
                pb.ReadSuccess(
                    path=args.path,
                    content="".join(lines[offset:end]),
                    total_lines=len(lines),
                    file_size=len(data),
                    truncated=offset > 0 or end < len(lines),
                    range_applied=bool(args.offset or args.limit),
                )
            )
        return reply
