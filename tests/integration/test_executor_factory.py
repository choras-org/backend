import unittest
from unittest.mock import patch, MagicMock

from app.services.executors.factory import executor_factory
from app.types import ResourceType
from app.services.executors.cloud_executor import CloudExecutor
from app.services.discovery_service import discover_container_image, discover_entry_file
from config import CloudConfig


class ExecutorFactoryEdgeCaseTests(unittest.TestCase):
    
    def test_invalid_resource_type_raises_value_error(self):
        """Invalid resourceType → ValueError (no silent default)."""
        invalid_types = ["GPU", None, 999, ""]  # Edge cases
        
        for invalid_type in invalid_types:
            with self.subTest(invalid_type=invalid_type):
                with self.assertRaises(ValueError, msg=f"{invalid_type} should raise ValueError"):
                    executor_factory(invalid_type)
        
        print("✅ All invalid ResourceTypes → ValueError (no silent fallback)")

    @patch('app.services.discovery_service.discover_container_image')
    @patch('app.services.executors.factory.CloudExecutor')
    def test_discover_container_image_none_calls_cloud_executor(self, mock_cloud_exec, mock_discover_image):
        """discover_container_image() → None → CloudExecutor still called (image=None)."""
        mock_discover_image.return_value = None  # Method in DB but not discoverable
        
        executor = executor_factory(ResourceType.CLOUD)
        
        mock_cloud_exec.assert_called_once()  # Still instantiates!
        args = mock_cloud_exec.call_args[1]
        self.assertIsNone(args.get('container_image'), 
            "❌ CloudExecutor should receive container_image=None")
        print("✅ container_image=None → CloudExecutor still instantiated")

    @patch('app.services.discovery_service.discover_entry_file')
    @patch('app.services.executors.factory.CloudExecutor')
    def test_discover_entry_file_none_cloud_executor_entry_file_none(self, mock_cloud_exec, mock_discover_entry):
        """discover_entry_file() → None → CloudExecutor(entry_file=None)."""
        mock_discover_entry.return_value = None  # Breaks _execute_singularity_image
        
        executor = executor_factory(ResourceType.CLOUD, entry_file=None)  # Explicit test
        
        mock_cloud_exec.assert_called_once_with(
            CloudConfig.CLOUD_EXECUTOR_HOST,           # Positional arg 1
            CloudConfig.CLOUD_EXECUTOR_USER,           # Positional arg 2
            key_path=CloudConfig.CLOUD_EXECUTOR_KEY_PATH,  # Keyword arg 3
            remote_work_dir=CloudConfig.CLOUD_EXECUTOR_DIRECTORY,  # Keyword arg 4
            entry_file=None                            # Keyword arg 5 ✅ Tested!
    )
        print("✅ entry_file=None → passed to CloudExecutor (will break execute!)")

