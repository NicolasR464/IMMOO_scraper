from typing import Any

from google.auth.credentials import Credentials
from googleapiclient.discovery import build


class AppsScriptDeployer:
    def __init__(self, credentials: Credentials):
        """Initialize Apps Script API client using existing OAuth credentials."""
        # Type annotate as Any to bypass dynamic resource inspection warnings
        self.service: Any = build("script", "v1", credentials=credentials)

    def inject_collaborator_script(self, spreadsheet_id: str) -> str:
        """Binds a new Apps Script project to the spreadsheet and writes the onOpen trigger."""
        try:
            # 1. Create container-bound Apps Script project attached to the Spreadsheet
            create_request = {
                "title": "IMMOO Collaborator Rating Automation",
                "parentId": spreadsheet_id,
            }

            # type: ignore / Any annotation handles dynamic .projects() lookup
            project = (
                self.service.projects().create(body=create_request).execute()  # type: ignore[attr-defined]
            )
            script_id = project.get("scriptId")

            # 2. Define JavaScript code for onOpen with Column Protection
            js_code = """
function onOpen() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const user = Session.getActiveUser();
  const userEmail = user.getEmail();
  
  if (!userEmail) return;
  
  const userName = userEmail.split('@')[0];
  const headerRow = sheet.getRange(2, 1, 1, sheet.getLastColumn()).getValues()[0];
  const userHeader = `Rating (${userName})`;
  
  if (!headerRow.includes(userHeader)) {
    const avgRatingIdx = headerRow.indexOf("Avg Rating");
    const insertIdx = avgRatingIdx !== -1 ? avgRatingIdx + 1 : sheet.getLastColumn();
    
    sheet.insertColumnBefore(insertIdx);
    sheet.getRange(2, insertIdx).setValue(userHeader);
    
    const ratingRange = sheet.getRange(3, insertIdx, 198, 1);
    const rule = SpreadsheetApp.newDataValidation()
      .requireNumberBetween(1, 5)
      .setAllowInvalid(true)
      .build();
    ratingRange.setDataValidation(rule);
    
    const fullColumnRange = sheet.getRange(1, insertIdx, sheet.getMaxRows(), 1);
    const protection = fullColumnRange.protect().setDescription(`Protected Column for ${userName}`);
    
    protection.removeEditors(protection.getEditors());
    protection.addEditor(userEmail);
    
    if (protection.canDomainEdit()) {
      protection.setDomainEdit(false);
    }
  }
}
"""

            # 3. Update project content
            update_request = {
                "files": [
                    {
                        "name": "Code",
                        "type": "SERVER_JS",
                        "source": js_code,
                    },
                    {
                        "name": "appsscript",
                        "type": "JSON",
                        "source": (
                            '{"timeZone":"Europe/Paris","exceptionLogging":"CLOUD"}'
                        ),
                    },
                ]
            }

            self.service.projects().updateContent(  # type: ignore[attr-defined]
                scriptId=script_id, body=update_request
            ).execute()

            print(
                f"[SCRIPT DEPLOYER] Successfully bound Apps Script (ID: {script_id}) to Spreadsheet."
            )
            return script_id

        except Exception as e:
            print(f"[ERROR] Failed to inject Apps Script programmatically: {e}")
            raise e
