"""MCP and structural reads must not need the heavy vector-storage imports."""

import subprocess
import sys
from pathlib import Path


def test_server_and_structural_reads_work_without_storage_imports(built_doc_dir: Path) -> None:
    code = """
import asyncio, builtins, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'lancedb', 'pyarrow'}:
        raise AssertionError('Structural read imported vector storage: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from pathlib import Path
from cairn.mcp.server import build_repo_server
from cairn.tools.base import DocumentIndex
from cairn.tools.outline import outline
from cairn.tools.get_section import get_section
index = DocumentIndex.load(Path(sys.argv[1]))
async def check():
    assert (await outline(index)).data['tree']
    assert (await get_section(index, id='introduction', level='full')).data['content']
asyncio.run(check())
assert 'lancedb' not in sys.modules and 'pyarrow' not in sys.modules
print('PASS')
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(built_doc_dir)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout
