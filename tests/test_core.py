"""
Ozempic Unit Tests
Tests for core functionality: file validation, thickness processing, preview generation.
"""

import os
import sys
import pytest
import tempfile
from pathlib import Path

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

# The service reads its admin password from the environment; tests supply their own.
TEST_ADMIN_PASSWORD = "test-admin-password"
os.environ.setdefault("OZEMPIC_ADMIN_PASSWORD", TEST_ADMIN_PASSWORD)

from engine import process_step_file, validate_step_file
from preview import step_file_to_mesh_data
from auth import create_token, verify_token, authenticate_user


class TestValidation:
    """Test file validation functionality."""
    
    def test_validate_step_file(self):
        """Test validating a valid STEP file."""
        test_file = Path(__file__).parent / 'test_step.step'
        if not test_file.exists():
            pytest.skip("Test file not found")
        
        result = validate_step_file(str(test_file))
        
        # result is a dataclass, convert to dict
        if hasattr(result, '__dict__'):
            result_dict = result.__dict__
        else:
            result_dict = result
        
        assert result_dict['valid'] is True
        assert result_dict['num_shapes'] == 1
        assert result_dict['num_faces'] == 6
        assert result_dict['num_edges'] == 24
        assert result_dict['num_vertices'] == 48
        assert result_dict['volume'] == 1000000.0
        assert result_dict['surface_area'] == 60000.0
    
    def test_validate_invalid_file(self):
        """Test validating an invalid file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xyz', delete=False) as f:
            f.write("invalid content")
            temp_path = f.name
        
        try:
            result = validate_step_file(temp_path)
            # result is a dataclass, convert to dict
            if hasattr(result, '__dict__'):
                result_dict = result.__dict__
            else:
                result_dict = result
            
            assert result_dict.get('valid') is False
            assert len(result_dict.get('errors', [])) > 0
        finally:
            os.unlink(temp_path)


class TestThicknessProcessing:
    """Test thickness modification functionality."""
    
    def test_process_default_thickness(self):
        """Test processing with default thickness (2.0mm)."""
        test_file = Path(__file__).parent / 'test_step.step'
        if not test_file.exists():
            pytest.skip("Test file not found")
        
        with tempfile.NamedTemporaryFile(suffix='.step', delete=False) as f:
            output_path = f.name
        
        try:
            result = process_step_file(str(test_file), 2.0, output_path)
            
            assert result['status'] == 'success'
            assert result['input_volume'] == 1000000.0
            assert result['output_volume'] < 1000000.0  # Volume should decrease
            assert result['volume_change'] < 0  # Negative change
            assert os.path.exists(output_path)
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)
    
    def test_process_various_thicknesses(self):
        """Test processing with different thickness values."""
        test_file = Path(__file__).parent / 'test_step.step'
        if not test_file.exists():
            pytest.skip("Test file not found")
        
        thicknesses = [0.1, 1.0, 2.0, 5.0, 10.0, 20.0]
        volumes = {}
        
        for thickness in thicknesses:
            with tempfile.NamedTemporaryFile(suffix='.step', delete=False) as f:
                output_path = f.name
            
            try:
                result = process_step_file(str(test_file), thickness, output_path)
                volumes[thickness] = result['output_volume']
            finally:
                if os.path.exists(output_path):
                    os.unlink(output_path)
        
        # Thicker walls should result in less volume (more material removed)
        assert volumes[0.1] > volumes[1.0] > volumes[2.0] > volumes[5.0]
    
    def test_process_extreme_thickness(self):
        """Test processing with extreme thickness values."""
        test_file = Path(__file__).parent / 'test_step.step'
        if not test_file.exists():
            pytest.skip("Test file not found")
        
        # Very thick wall (should still work)
        with tempfile.NamedTemporaryFile(suffix='.step', delete=False) as f:
            output_path = f.name
        
        try:
            result = process_step_file(str(test_file), 20.0, output_path)
            assert result['status'] == 'success'
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)


class TestPreviewGeneration:
    """Test 3D preview generation."""
    
    def test_preview_generation(self):
        """Test generating preview mesh data."""
        test_file = Path(__file__).parent / 'test_step.step'
        if not test_file.exists():
            pytest.skip("Test file not found")
        
        result = step_file_to_mesh_data(str(test_file))
        
        assert result['success'] is True
        assert len(result['vertices']) > 0
        assert len(result['indices']) > 0
        assert result['triangles'] == 12  # 6 geometric faces × 2 triangles each = 12 triangle faces
        assert result['faces'] == 12  # faces field counts triangles in mesh
        assert result['volume'] == 1000000.0
        assert result['surface_area'] == 60000.0
        assert result['bounding_box'] is not None
    
    def test_preview_bounds(self):
        """Test that preview bounding box is reasonable."""
        test_file = Path(__file__).parent / 'test_step.step'
        if not test_file.exists():
            pytest.skip("Test file not found")
        
        result = step_file_to_mesh_data(str(test_file))
        
        bbox = result['bounding_box']
        assert bbox['size'][0] > 0
        assert bbox['size'][1] > 0
        assert bbox['size'][2] > 0
        assert bbox['center'][0] > 0
        assert bbox['center'][1] > 0
        assert bbox['center'][2] > 0


class TestAuthentication:
    """Test authentication functionality."""
    
    def test_create_token(self):
        """Test JWT token creation."""
        token = create_token("testuser", "user")
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_verify_token(self):
        """Test JWT token verification."""
        token = create_token("testuser", "user")
        payload = verify_token(token)
        
        assert payload['sub'] == "testuser"
        assert payload['role'] == "user"
        assert 'exp' in payload
        assert 'iat' in payload
    
    def test_authenticate_user(self):
        """Test user authentication."""
        # Valid credentials
        user = authenticate_user("admin", TEST_ADMIN_PASSWORD)
        assert user is not None
        assert user['username'] == "admin"
        assert user['role'] == "admin"
        
        # Invalid credentials
        user = authenticate_user("admin", "wrong_password")
        assert user is None
        
        # Non-existent user
        user = authenticate_user("nonexistent", "password")
        assert user is None
    
    def test_token_expiry(self):
        """Test that token expires correctly."""
        # This test would need to mock time to work properly
        # For now, just verify token creation and verification work
        token = create_token("testuser", "user")
        payload = verify_token(token)
        
        assert 'exp' in payload
        # Expiry should be in the future
        from datetime import datetime, timezone
        exp = datetime.fromtimestamp(payload['exp'], tz=timezone.utc)
        assert exp > datetime.now(timezone.utc)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
