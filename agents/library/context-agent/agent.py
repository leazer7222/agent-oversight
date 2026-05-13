import os
import sys
import json
import io
import pypdf
import docx2txt
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
            url=os.environ.get("OVERSIGHT_URL", "http://localhost:3000"),  # SDK appends /api/ingest
            secret=os.environ.get("OVERSIGHT_SECRET") or os.environ.get("INGEST_SECRET")
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

    def search_docs(self, query: str, folder_id: str) -> List[Dict[str, Any]]:
        """Search for documents in Google Drive, including subfolders for target ID."""
        print(f"Searching GDrive for: {query} (Root Folder: {folder_id})")
        if not self.drive_service:
            print("[Warning] No Drive service available.")
            return []
            
        try:
            # 1. Get all subfolders first
            sub_q = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder'"
            folder_results = self.drive_service.files().list(
                q=sub_q,
                fields="files(id, name)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora="allDrives"
            ).execute()
            folders = folder_results.get('files', [])
            folder_ids = [folder_id] + [f['id'] for f in folders]
            
            print(f"  [Debug] Found {len(folders)} subfolders. Searching in all {len(folder_ids)} locations.")
            
            # Supported MimeTypes
            mimetypes = [
                "application/vnd.google-apps.document", # Google Doc
                "application/pdf",                      # PDF
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document" # DOCX
            ]
            
            all_files = []
            # 2. Search for documents in each folder
            for fid in folder_ids:
                mime_q = "(" + " or ".join([f"mimeType='{m}'" for m in mimetypes]) + ")"
                q = f"'{fid}' in parents and {mime_q}"
                results = self.drive_service.files().list(
                    q=q,
                    fields="nextPageToken, files(id, name, mimeType)",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    corpora="allDrives"
                ).execute()
                all_files.extend(results.get('files', []))
            
            return all_files
        except Exception as e:
            print(f"[Error] Failed to search drive: {e}")
            return []

    def read_doc(self, file_id: str, mime_type: str) -> str:
        """Read and extract text from Google Drive documents (Google Docs, PDF, DOCX)."""
        print(f"Reading GDrive file ({mime_type}): {file_id}")
        if not self.drive_service:
            return ""
            
        try:
            if mime_type == 'application/vnd.google-apps.document':
                # Export Google Doc as plain text
                request = self.drive_service.files().export_media(fileId=file_id, mimeType='text/plain')
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False:
                    status, done = downloader.next_chunk()
                return fh.getvalue().decode('utf-8')
            
            elif mime_type == 'application/pdf':
                # Download PDF and extract text
                request = self.drive_service.files().get_media(fileId=file_id)
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False:
                    status, done = downloader.next_chunk()
                
                # Extract text using pypdf
                pdf_reader = pypdf.PdfReader(io.BytesIO(fh.getvalue()))
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text
            
            elif mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                # Download DOCX and extract text
                request = self.drive_service.files().get_media(fileId=file_id)
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False:
                    status, done = downloader.next_chunk()
                
                # Extract text using docx2txt
                text = docx2txt.process(io.BytesIO(fh.getvalue()))
                return text
                
            return ""
        except Exception as e:
            print(f"[Error] Failed to read/extract doc {file_id}: {e}")
            return ""

    def run(self, query: str, company_id: Optional[str] = None, folder_id: Optional[str] = None):
        # Prioritization: Input Arg -> Env Var -> Hardcoded Default
        target_folder = folder_id or os.environ.get("CONTEXT_FOLDER_ID", "1dVzlTU8QUq__8YefaE_m7Ue8cNkTjRz0")
        recursive = os.environ.get("CONTEXT_RECURSIVE", "true").lower() == "true"
        
        with self.client.run(agent_id=self.agent_id, metadata={"query": query, "company_id": company_id}) as run:
            try:
                run.report(metadata={"step": "searching_documents", "folder_id": target_folder, "recursive": recursive})
                
                if recursive:
                    files = self.search_docs(query, target_folder)
                else:
                    # Supported MimeTypes for non-recursive list
                    mimetypes = [
                        "application/vnd.google-apps.document",
                        "application/pdf",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    ]
                    mime_q = "(" + " or ".join([f"mimeType='{m}'" for m in mimetypes]) + ")"
                    q = f"'{target_folder}' in parents and {mime_q}"
                    res = self.drive_service.files().list(
                        q=q, fields="files(id, name, mimeType)", supportsAllDrives=True, includeItemsFromAllDrives=True, corpora="allDrives"
                    ).execute()
                    files = res.get('files', [])
                
                # --- Surgical Filter (Optional via Env) ---
                include_list_raw = os.environ.get("CONTEXT_INCLUDE_LIST")
                if include_list_raw:
                    allowed_files = [name.strip() for name in include_list_raw.split(",")]
                    original_count = len(files)
                    files = [f for f in files if f['name'] in allowed_files]
                    print(f"ContextAgent: Surgical filter applied. Kept {len(files)} of {original_count} files.")
                
                print(f"ContextAgent found {len(files)} files in folder {target_folder}.")
                for f in files:
                    print(f" - {f['name']} ({f['mimeType']})")

                run.report(metadata={"step": "reading_documents", "count": len(files)})
                
                # Truncation limit (Optional via Env)
                max_chars = os.environ.get("CONTEXT_MAX_CHARS_PER_FILE")
                if max_chars:
                    max_chars = int(max_chars)

                results = []
                for f in files: 
                    content = self.read_doc(f["id"], f["mimeType"])
                    if content:
                        if max_chars:
                            content = content[:max_chars]
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
