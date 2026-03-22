import os
import sys
import json
from pathlib import Path
from typing import Optional, List, Dict, Any

# Add parent directory to path to import oversight
sys.path.append(str(Path(__file__).parent.parent.parent.parent / "python-sdk"))
from oversight import OversightClient

class ContextAgent:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        # In a real environment, these would be loaded from .env or passed in
        self.client = OversightClient(
            url=os.environ.get("OVERSIGHT_URL", "http://localhost:3000/api/agents/ingest"),
            secret=os.environ.get("OVERSIGHT_SECRET")
        )

    def search_docs(self, query: str, folder_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for documents in Google Drive.
        Note: This assumes the environment provides 'gdrive_search' tool.
        """
        print(f"Searching GDrive for: {query} (Folder: {folder_id or 'Root'})")
        # In a real MCP environment, the agent would call:
        # result = call_tool("gdrive", "gdrive_search", {"query": query, "folderId": folder_id})
        
        # Skeleton for actual integration:
        return [
            {"id": "doc_1", "name": "Project Overview", "mimeType": "application/vnd.google-apps.document"},
            {"id": "doc_2", "name": "Technical Spec", "mimeType": "application/vnd.google-apps.document"}
        ]

    def read_doc(self, file_id: str) -> str:
        """
        Read the content of a specific Google Drive file.
        Note: This assumes 'gdrive_read_file' tool is available.
        """
        print(f"Reading GDrive file: {file_id}")
        # result = call_tool("gdrive", "gdrive_read_file", {"fileId": file_id})
        return f"Content of document {file_id}..."

    def run(self, query: str, company_id: Optional[str] = None, folder_id: Optional[str] = "1dVzlTU8QUq__8YefaE_m7Ue8cNkTjRz0"):

        with self.client.run(agent_id=self.agent_id, metadata={"query": query, "company_id": company_id}) as run:
            try:
                run.report_step("searching_documents", {"query": query})
                files = self.search_docs(query, folder_id)
                
                run.report_step("reading_documents", {"count": len(files)})
                results = []
                for f in files[:2]: # Limit to first 2 docs for now
                    content = self.read_doc(f["id"])
                    results.append({"name": f["name"], "content": content})
                
                context = "\n\n".join([f"Source: {r['name']}\n{r['content']}" for r in results])
                
                run.report(metadata={"docs_processed": len(results)})
                
                return {
                    "context": context,
                    "docs": [f["name"] for f in files],
                    "status": "success"
                }
            except Exception as e:
                print(f"Error in ContextAgent: {e}")
                run.report(metadata={"error": str(e)})
                return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    # Test run
    AGENT_ID = os.environ.get("AGENT_ID", "context-agent-uuid-placeholder")
    agent = ContextAgent(agent_id=AGENT_ID)
    
    if len(sys.argv) > 1:
        query = sys.argv[1]
    else:
        query = "What is ReformAI?"
        
    result = agent.run(query=query)
    print(json.dumps(result, indent=2))
