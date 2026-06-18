import unittest
from unittest.mock import AsyncMock, patch

import main as agent
from main import Input
from uipath.platform.documents import ProjectType


class FakeExtractionResult:
    document_id = "document-id"

    def model_dump(self, by_alias=False):
        return {"DocumentId": self.document_id}


class FakeExtractionResponse:
    project_id = "00000000-0000-0000-0000-000000000000"
    extractor_id = "invoices"
    tag = None
    document_type_id = "invoices"
    project_type = ProjectType.PRETRAINED
    extraction_result = FakeExtractionResult()


class InputDefaultTests(unittest.TestCase):
    def test_validate_extraction_null_action_settings_use_model_defaults(self):
        payload = {
            "file_resource": {
                "ID": "e826fe01-8249-46c0-0fc7-08deab90440b",
                "FullName": "Sample Invoice.pdf",
                "MimeType": "application/pdf",
                "Metadata": {},
            },
            "pipeline_json": {
                "extraction_project_extractors": {
                    "00000000-0000-0000-0000-000000000000": {
                        "id": "00000000-0000-0000-0000-000000000000",
                        "name": "Pretrained",
                        "project_type": "Pretrained",
                        "extractor_id": "invoices",
                    }
                },
                "validate_extraction": True,
                "perform_extraction": True,
            },
            "validate_extraction": True,
            "action_catalog": None,
            "action_folder": None,
            "storage_bucket_name": None,
            "storage_bucket_directory_path": None,
        }

        input_data = Input.model_validate(payload)

        self.assertEqual(input_data.action_catalog, "default_du_actions")
        self.assertEqual(input_data.action_folder, "Shared/nn_IXP")
        self.assertEqual(input_data.storage_bucket_name, "du_storage_bucket")
        self.assertEqual(input_data.storage_bucket_directory_path, "/")


class ValidationActionFolderTests(unittest.IsolatedAsyncioTestCase):
    async def test_validate_extraction_sends_action_folder_name_to_documents_api(self):
        payload = {
            "file_resource": {
                "ID": "e826fe01-8249-46c0-0fc7-08deab90440b",
                "FullName": "Sample Invoice.pdf",
            },
            "pipeline_json": {
                "extraction_project_extractors": {
                    "00000000-0000-0000-0000-000000000000": {
                        "name": "Pretrained",
                        "project_type": "Pretrained",
                        "extractor_id": "invoices",
                    }
                }
            },
            "validate_extraction": True,
            "action_folder": "Shared/nn_IXP",
        }
        input_data = Input.model_validate(payload)
        create_validation_action = AsyncMock(return_value=None)

        with (
            patch.object(agent, "_download_file_resource", new=AsyncMock()),
            patch.object(
                agent,
                "_extract_document",
                new=AsyncMock(return_value=FakeExtractionResponse()),
            ),
            patch.object(
                type(agent.sdk.documents),
                "create_validate_extraction_action_async",
                new=create_validation_action,
            ),
        ):
            await agent._run_async(input_data)

        self.assertEqual(
            create_validation_action.call_args.kwargs["action_folder"],
            "nn_IXP",
        )


if __name__ == "__main__":
    unittest.main()
