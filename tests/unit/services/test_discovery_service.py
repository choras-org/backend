import unittest
import os
import json
from pathlib import Path

from app.services import discovery_service
from tests.unit import BaseTestCase
from config import DefaultConfig


class DiscoveryServiceUnitTests(BaseTestCase):
    def setUp(self):
        """
        Set up method to initialize variables and preconditions.
        """
        super().setUp()

    def test_discover_methods_real_config(self):
        """
        Test that discover_methods correctly reads and filters real config.
        """
        with self.app.app_context():
            methods = discovery_service.discover_methods()
        
        discovered_types = [cfg.get("simulationType") for cfg in methods]
        self.assertTrue(
            len(methods) > 0,
            f"❌ discover_methods returned empty list. No valid methods found in config."
        )
        self.assertTrue(
            any(cfg.get("simulationType") == "DG" for cfg in methods),
            f"❌ DG method missing from discovered methods. Found: {discovered_types}"
        )
        self.assertTrue(
            any(cfg.get("simulationType") == "DE" for cfg in methods),
            f"❌ DE method missing from discovered methods. Found: {discovered_types}"
        )
        print(f"✅ discover_methods found {len(methods)} methods: {discovered_types}")

    def test_discover_method_names(self):
        """
        Test that discover_method_names extracts method names correctly.
        """
        with self.app.app_context():
            method_names = discovery_service.discover_method_names()
        
        self.assertTrue(
            len(method_names) > 0,
            "❌ discover_method_names returned empty list. No method names discovered."
        )
        self.assertIn(
            "DG",
            method_names,
            f"❌ 'DG' missing from method names. Got: {method_names}"
        )
        self.assertIn(
            "DE",
            method_names,
            f"❌ 'DE' missing from method names. Got: {method_names}"
        )
        print(f"✅ discover_method_names returned: {method_names}")

    def test_discover_container_image(self):
        """
        Test discover_container_image: specific DG/DE checks + all methods validation.
        """
        with self.app.app_context():
            # Specific method checks
            dg_image = discovery_service.discover_container_image("DG")
            de_image = discovery_service.discover_container_image("DE")
            
            # Generic validation for ALL discovered methods
            all_methods = discovery_service.discover_methods()
            
            # 1. DG specific
            self.assertEqual(
                dg_image,
                "dg_image:latest",
                "❌ DG container_image should be 'dg_image:latest'"
            )
            
            # 2. DE specific  
            self.assertEqual(
                de_image,
                "de_image:latest",
                "❌ DE container_image should be 'de_image:latest'"
            )
            
            # 3. ALL methods must have container_image field
            missing_container_methods = []
            for cfg in all_methods:
                sim_type = cfg.get("simulationType")
                container_img = cfg.get("containerImage")
                if not container_img:
                    missing_container_methods.append(sim_type)
            
            self.assertFalse(
                missing_container_methods,
                f"❌ Methods missing container image: {missing_container_methods}"
            )
            
            print(f"✅ DG:'dg_image:latest' DE:'de_image:latest' "
                f"All {len(all_methods)} methods have container_image")

    def test_discover_entry_file(self):
        """
        Test discover_entry_file: specific DG/DE checks + all methods validation.
        """
        with self.app.app_context():
            # Specific method checks
            dg_entry = discovery_service.discover_entry_file("DG")
            de_entry = discovery_service.discover_entry_file("DE")
            
            # Generic validation for ALL discovered methods
            all_methods = discovery_service.discover_methods()
            
            # 1. DG specific
            self.assertEqual(
                dg_entry,
                "DGinterface.py",
                "❌ DG entryFile should be 'DGinterface.py'"
            )
            
            # 2. DE specific
            self.assertEqual(
                de_entry,
                "DEinterface.py",
                "❌ DE entryFile should be 'DEinterface.py'"
            )
            
            # 3. ALL methods must have entryFile field
            missing_entry_methods = []
            for cfg in all_methods:
                sim_type = cfg.get("simulationType")
                entry_file = cfg.get("entryFile")
                if not entry_file:
                    missing_entry_methods.append(sim_type)
            
            self.assertFalse(
                missing_entry_methods,
                f"❌ Methods missing entryFile: {missing_entry_methods}"
            )
            
            print(f"✅ DG:'DGInterface.py' DE:'DEInterface.py' "
                f"All {len(all_methods)} methods have entryFile")

    def test_discover_methods_config_structure_validation(self):
        """
        Validate methods-config.json is array with required fields.
        """
        with self.app.app_context():
            methods = discovery_service.discover_methods()
        
        # 1. Must be array
        self.assertIsInstance(
            methods,
            list,
            "❌ discover_methods must return a list (array), got different type"
        )
        
        # 2. Each item must have compulsory fields
        compulsory_fields = {"simulationType", "label", "containerImage", "entryFile"}
        for i, cfg in enumerate(methods):
            missing_fields = compulsory_fields - set(cfg.keys())
            self.assertFalse(
                missing_fields,
                f"❌ Method {i} (simType: {cfg.get('simulationType', 'unknown')}) "
                f"missing compulsory fields: {missing_fields}"
            )
        
        print(f"✅ Config structure validation passed: {len(methods)} valid methods")

    def test_discover_methods_settings_files_exist(self):
        """
        Validate OPTIONAL 'settings' files: if referenced in config, must exist.
        Methods without 'settings' field are valid (optional field).
        """
        with self.app.app_context():
            methods = discovery_service.discover_methods()
            
            # Categorize methods
            methods_with_settings = 0
            missing_settings = []
            valid_settings = []
            
            for i, cfg in enumerate(methods):
                settings_file = cfg.get("settings")
                if settings_file:
                    methods_with_settings += 1
                    settings_path = Path(DefaultConfig.SETTINGS_FILE_FOLDER) / settings_file
                    if settings_path.exists():
                        valid_settings.append((cfg["simulationType"], settings_file))
                    else:
                        missing_settings.append((cfg["simulationType"], settings_file))
            
            total_methods = len(methods)
            methods_without_settings = total_methods - methods_with_settings
            
            # Build descriptive report
            report = []
            if methods_without_settings > 0:
                report.append(f"📝 {methods_without_settings} methods have no settings file (OK)")
            if len(valid_settings) > 0:
                report.append(f"✅ {len(valid_settings)} settings files found")
            if len(missing_settings) > 0:
                report.append(f"❌ {len(missing_settings)} settings files MISSING:")
                for method, file in missing_settings:
                    report.append(f"  {method}: {file}")
            
            error_msg = "\n".join(report)
            
            # Fail only if referenced files are missing
            self.assertFalse(
                missing_settings,
                f"❌ Settings validation failed:\n{error_msg}"
            )
            
            # Success message with breakdown
            print(f"""
                ✅ Settings validation PASSED!
                📊 Breakdown:
                📝 {methods_without_settings}/{total_methods} methods: no settings (optional ✓)
                ✅ {len(valid_settings)} settings files: exist ✓
                ❌ {len(missing_settings)} settings files: missing ✗
                📁 Checked at: {DefaultConfig.SETTINGS_FILE_FOLDER}
            """)
