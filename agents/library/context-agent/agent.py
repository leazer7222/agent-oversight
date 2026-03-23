import os
import sys
import json
import io
from pathlib import Path
from typing import Optional, List, Dict, Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# Add parent directory to path to import oversight
import_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../python-sdk"))
if import_dir not in sys.path:
    sys.path.append(import_dir)
from oversight import OversightClient

class ContextAgent:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.client = OversightClient(
            url=os.environ.get("OVERSIGHT_URL", "http://localhost:3000/api/agents/ingest"),
            secret=os.environ.get("OVERSIGHT_SECRET")
        )
        
        # Initialize Google Drive Service
        key_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY", r"C:\Users\cjlea\Key\reformai-agent-dd4d7e12c73f.json")
        self.drive_service = None
        if os.path.exists(key_path):
            creds = service_account.Credentials.from_service_account_file(
                key_path, scopes=['https://www.googleapis.com/auth/drive.readonly']
            )
            self.drive_service = build('drive', 'v3', credentials=creds)
        else:
            print(f"[Warning] Google Service Account key not found at {key_path}")

    def search_docs(self, query: str, folder_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search for documents in Google Drive."""
        print(f"Searching GDrive for: {query} (Folder: {folder_id or 'Root'})")
        if not self.drive_service:
            print("[Warning] No Drive service available. Returning mock.")
            return []
            
        try:
            q = f"mimeType='application/vnd.google-apps.document'"
            if folder_id:
                q += f" and '{folder_id}' in parents"
                
            results = self.drive_service.files().list(
                q=q,
                fields="nextPageToken, files(id, name, mimeType)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora="allDrives"
            ).execute()
            items = results.get('files', [])
            return items
        except Exception as e:
            print(f"[Error] Failed to search drive: {e}")
            return []

    def read_doc(self, file_id: str) -> str:
        """Read the content of a specific Google Drive document (Google Doc format)."""
        print(f"Reading GDrive file: {file_id}")
        if not self.drive_service:
            return ""
            
        try:
            request = self.drive_service.files().export_media(fileId=file_id, mimeType='text/plain')
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            return fh.getvalue().decode('utf-8')
        except Exception as e:
            print(f"[Error] Failed to read doc {file_id}: {e}")
            return ""

    def run(self, query: str, company_id: Optional[str] = None, folder_id: Optional[str] = "1dVzlTU8QUq__8YefaE_m7Ue8cNkTjRz0"):
        with self.client.run(agent_id=self.agent_id, metadata={"query": query, "company_id": company_id}) as run:
            try:
                run.report(metadata={"step": "searching_documents", "query": query})
                files = self.search_docs(query, folder_id)
                
                run.report(metadata={"step": "reading_documents", "count": len(files)})
                results = []
                for f in files: # Read all documents found
                    content = self.read_doc(f["id"])
                    if content:
                        results.append({"name": f["name"], "content": content})
                
                context = "\n\n".join([f"Source: {r['name']}\n{r['content']}" for r in results])
                
                run.report(metadata={"docs_processed": len(results)})
                
                return {
                    "context": context,
                    "docs": [f["name"] for f in files],
                    "status": "success",
                    "raw_files": results
                }
            except Exception as e:
                print(f"Error in ContextAgent: {e}")
                run.report(metadata={"error": str(e)})
                return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    AGENT_ID = os.environ.get("AGENT_ID", "a1b2c3d4-e5f6-47a8-b9c0-d1e2f3a4b5c6")
    agent = ContextAgent(agent_id=AGENT_ID)
    result = agent.run(query="What is ReformAI?")
    print(json.dumps(result, indent=2))
