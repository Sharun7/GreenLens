"""
Script to add copyright notice to all Python files in the project.
"""
import os
from pathlib import Path

COPYRIGHT_NOTICE = """# Copyright (c) 2026 Sharun Tomy
# Licensed under BUSL-1.1. See LICENSE file for details.
# Commercial use prohibited without written permission.

"""

def add_copyright_to_file(filepath):
    """Add copyright notice to a Python file if not already present."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if copyright already exists
        if 'Copyright (c) 2026 Sharun Tomy' in content:
            print(f"  ⏭️  Skipped (already has copyright): {filepath}")
            return False
        
        # Add copyright at the top
        new_content = COPYRIGHT_NOTICE + content
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print(f"  ✅ Added copyright: {filepath}")
        return True
    
    except Exception as e:
        print(f"  ❌ Error processing {filepath}: {e}")
        return False

def main():
    """Find all Python files and add copyright notice."""
    project_root = Path(__file__).parent
    
    # Directories to process
    directories = [
        'ai_features',
        'business',
        'dashboard',
        'data_ingestion',
        'greenlens',
        'greenwash_detector',
        'pricing_analysis',
        'risk_management',
        'risk_scoring',
    ]
    
    print("="*60)
    print("Adding Copyright Notice to Python Files")
    print("="*60)
    
    total_files = 0
    updated_files = 0
    
    for directory in directories:
        dir_path = project_root / directory
        if not dir_path.exists():
            print(f"\n⚠️  Directory not found: {directory}")
            continue
        
        print(f"\n📁 Processing: {directory}/")
        
        # Find all .py files recursively
        py_files = list(dir_path.rglob('*.py'))
        
        for py_file in py_files:
            total_files += 1
            if add_copyright_to_file(py_file):
                updated_files += 1
    
    # Also process root-level Python files
    print(f"\n📁 Processing: root directory")
    for py_file in project_root.glob('*.py'):
        if py_file.name != 'add_copyright.py':  # Skip this script itself
            total_files += 1
            if add_copyright_to_file(py_file):
                updated_files += 1
    
    print("\n" + "="*60)
    print(f"✅ Complete!")
    print(f"   Total files processed: {total_files}")
    print(f"   Files updated: {updated_files}")
    print(f"   Files skipped: {total_files - updated_files}")
    print("="*60)

if __name__ == '__main__':
    main()
