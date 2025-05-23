#!/usr/bin/env python3
"""
Advanced Codebase Export Tool for LLM Consumption - FULL VERSION
================================================================

This script generates a comprehensive, structured export of the codebase
specifically optimized for Large Language Models that need to understand,
analyze, and modify the code effectively.

Features:
- Hierarchical project structure with descriptions
- Categorized file organization
- FULL file content inclusion (not truncated)
- Dependency analysis
- Configuration overview
- Error context from logs
- Documentation integration
- Code metrics and insights
"""

import os
import ast
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional

class LLMCodebaseExporter:
    def __init__(self, root_path: str = '.'):
        self.root = Path(root_path).resolve()
        self.output_file = self.root / 'LLM_CODEBASE_EXPORT.md'
        
        # More conservative ignore patterns - we want MORE content
        self.ignore_dirs = {
            '.git', '__pycache__', 'venv', 'env', '.venv', 
            '.mypy_cache', '.pytest_cache', '.idea', '.vscode', 'node_modules',
            'dist', 'build', '.eggs', '.tox', '.coverage', '.cache'
        }
        
        self.ignore_files = {
            'state.sqlite', '.env'  # Only truly sensitive files
        }
        
        self.ignore_extensions = {
            '.pyc', '.pyo', '.sqlite', '.exe', '.dll', '.so',
            '.zip', '.tar', '.gz', '.rar', '.7z', '.egg-info'
        }
        
        # File categorization for structured presentation
        self.file_categories = {
            'Core Application': ['app.py', 'main.py', 'run.py'],
            'Configuration': ['config.py', 'settings.py', '.env.example', 'alembic.ini'],
            'Dependencies': ['requirements.txt', 'setup.py', 'pyproject.toml', 'Pipfile'],
            'Documentation': ['README.md', '*.md', 'DEPLOYMENT_GUIDE.md', 'QUICK_START.md'],
            'Tests': ['test_*.py', '*_test.py', 'conftest.py'],
            'Database': ['*models.py', 'migrations/', 'alembic/'],
            'Bot Logic': ['bot_core/', 'core_logic/'],
            'Tools & Utilities': ['tools/', 'utils/', 'utils.py'],
            'Authentication': ['user_auth/', 'auth/'],
            'Workflows': ['workflows/'],
            'Docker & Deployment': ['Dockerfile', 'docker-compose.yml', 'deploy.*'],
            'Health & Monitoring': ['health_checks.py', 'monitor_*.py']
        }

    def analyze_python_file(self, file_path: Path) -> Dict:
        """Extract metadata from Python files"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            tree = ast.parse(content)
            
            classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
            imports = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend([alias.name for alias in node.names])
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    imports.extend([f"{module}.{alias.name}" for alias in node.names])
            
            # Get docstring
            docstring = ast.get_docstring(tree) or ""
            
            return {
                'classes': classes,
                'functions': functions,
                'imports': imports[:15],  # Increased from 10
                'docstring': docstring[:300] + "..." if len(docstring) > 300 else docstring,
                'lines': len(content.splitlines())
            }
        except Exception as e:
            return {'error': str(e), 'lines': 0}

    def get_file_category(self, file_path: Path) -> str:
        """Categorize file based on name and path"""
        rel_path = file_path.relative_to(self.root)
        path_str = str(rel_path).lower()
        
        for category, patterns in self.file_categories.items():
            for pattern in patterns:
                if pattern.endswith('/') and pattern[:-1] in path_str:
                    return category
                elif pattern.startswith('*') and path_str.endswith(pattern[1:]):
                    return category
                elif pattern == file_path.name:
                    return category
                elif pattern.replace('*', '') in file_path.name:
                    return category
        
        return 'Other'

    def should_ignore(self, path: Path) -> bool:
        """Check if path should be ignored - MUCH more permissive now"""
        if path.is_dir():
            return path.name in self.ignore_dirs
        else:
            return (path.name in self.ignore_files or 
                   path.suffix in self.ignore_extensions or
                   path.stat().st_size > 50 * 1024 * 1024)  # Increased from 10MB to 50MB

    def scan_codebase(self) -> Dict:
        """Scan entire codebase and organize information"""
        structure = {
            'files_by_category': {},
            'directory_tree': {},
            'python_modules': {},
            'total_files': 0,
            'total_lines': 0
        }
        
        for category in self.file_categories.keys():
            structure['files_by_category'][category] = []
        structure['files_by_category']['Other'] = []
        
        for file_path in self.root.rglob('*'):
            if self.should_ignore(file_path) or not file_path.is_file():
                continue
                
            rel_path = file_path.relative_to(self.root)
            category = self.get_file_category(file_path)
            
            file_info = {
                'path': str(rel_path),
                'size_kb': file_path.stat().st_size / 1024,
                'category': category
            }
            
            # Analyze Python files
            if file_path.suffix == '.py':
                analysis = self.analyze_python_file(file_path)
                file_info.update(analysis)
                structure['python_modules'][str(rel_path)] = analysis
                structure['total_lines'] += analysis.get('lines', 0)
            
            structure['files_by_category'][category].append(file_info)
            structure['total_files'] += 1
        
        return structure

    def read_file_safely(self, file_path: Path, max_lines: int = None) -> str:
        """Read file content with MUCH more generous limits"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                
                # Only truncate if max_lines is specified AND file is really huge
                if max_lines and len(lines) > max_lines:
                    content = ''.join(lines[:max_lines])
                    content += f"\n\n... [TRUNCATED - {len(lines) - max_lines} more lines] ..."
                else:
                    content = ''.join(lines)
                return content
        except Exception as e:
            return f"[ERROR READING FILE: {e}]"

    def generate_export(self):
        """Generate comprehensive LLM-friendly codebase export - FULL VERSION"""
        print("🚀 Starting FULL LLM Codebase Export...")
        
        structure = self.scan_codebase()
        
        with open(self.output_file, 'w', encoding='utf-8') as f:
            # Header
            f.write(f"""# 🤖 LLM-Optimized Codebase Export - COMPLETE VERSION
**Project**: Minimal Bot
**Export Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Total Files**: {structure['total_files']}
**Total Python Lines**: {structure['total_lines']:,}

---

""")
            
            # Project Overview
            f.write("""## 📋 PROJECT OVERVIEW

This appears to be a **Minimal Bot** project - an advanced chatbot/AI assistant with:
- **Multi-platform integration** (Teams, web interface)
- **Tool management system** (GitHub, Jira, Perplexity, etc.)
- **User authentication & authorization**
- **Database persistence** (SQLite + Redis)
- **Workflow management**
- **Health monitoring & deployment**

### 🏗️ Architecture Components:
- **bot_core/**: Core bot logic and handlers
- **core_logic/**: Agent loop and processing logic
- **tools/**: External tool integrations
- **user_auth/**: Authentication system
- **workflows/**: Business process workflows
- **utils/**: Shared utilities

---

""")
            
            # File Structure by Category
            f.write("## 📁 PROJECT STRUCTURE BY CATEGORY\n\n")
            
            for category, files in structure['files_by_category'].items():
                if not files:
                    continue
                    
                f.write(f"### {category}\n")
                for file_info in sorted(files, key=lambda x: x['path']):
                    size_str = f"{file_info['size_kb']:.1f}KB"
                    f.write(f"- `{file_info['path']}` ({size_str})")
                    
                    if 'classes' in file_info and file_info['classes']:
                        f.write(f" - Classes: {', '.join(file_info['classes'][:5])}")  # Show more classes
                    if 'functions' in file_info and file_info['functions']:
                        f.write(f" - Functions: {len(file_info['functions'])}")
                    
                    f.write("\n")
                f.write("\n")

            # Dependencies - FULL content
            f.write("## 📦 DEPENDENCIES & CONFIGURATION\n\n")
            
            # Requirements - COMPLETE
            req_file = self.root / 'requirements.txt'
            if req_file.exists():
                f.write("### requirements.txt (COMPLETE)\n```\n")
                f.write(self.read_file_safely(req_file))  # NO limit
                f.write("\n```\n\n")
            
            # Configuration - COMPLETE
            config_file = self.root / 'config.py'
            if config_file.exists():
                f.write("### config.py (COMPLETE)\n```python\n")
                f.write(self.read_file_safely(config_file))  # NO limit
                f.write("\n```\n\n")

            # COMPLETE Core Application Files
            f.write("## 🔑 CORE APPLICATION FILES (COMPLETE)\n\n")
            
            key_files = [
                'app.py',
                'state_models.py',
                'llm_interface.py',
                'utils.py'
            ]
            
            for filename in key_files:
                file_path = self.root / filename
                if file_path.exists():
                    f.write(f"### {filename} (COMPLETE)\n")
                    if filename in structure['python_modules']:
                        module_info = structure['python_modules'][filename]
                        if module_info.get('docstring'):
                            f.write(f"**Purpose**: {module_info['docstring']}\n\n")
                        if module_info.get('classes'):
                            f.write(f"**Classes**: {', '.join(module_info['classes'])}\n\n")
                    
                    f.write("```python\n")
                    f.write(self.read_file_safely(file_path))  # NO limit
                    f.write("\n```\n\n---\n\n")

            # COMPLETE Bot Core Components
            f.write("## 🤖 BOT CORE COMPONENTS (COMPLETE)\n\n")
            
            bot_core_dir = self.root / 'bot_core'
            if bot_core_dir.exists():
                for py_file in sorted(bot_core_dir.rglob('*.py')):
                    if self.should_ignore(py_file):
                        continue
                    rel_path = py_file.relative_to(self.root)
                    f.write(f"### {rel_path} (COMPLETE)\n")
                    f.write("```python\n")
                    f.write(self.read_file_safely(py_file))  # NO limit
                    f.write("\n```\n\n---\n\n")

            # COMPLETE Core Logic
            f.write("## 🧠 CORE LOGIC (COMPLETE)\n\n")
            
            core_logic_dir = self.root / 'core_logic'
            if core_logic_dir.exists():
                for py_file in sorted(core_logic_dir.rglob('*.py')):
                    if self.should_ignore(py_file):
                        continue
                    rel_path = py_file.relative_to(self.root)
                    f.write(f"### {rel_path} (COMPLETE)\n")
                    f.write("```python\n")
                    f.write(self.read_file_safely(py_file))  # NO limit
                    f.write("\n```\n\n---\n\n")

            # COMPLETE Tools & Integrations
            f.write("## 🛠️ TOOLS & INTEGRATIONS (COMPLETE)\n\n")
            
            tools_dir = self.root / 'tools'
            if tools_dir.exists():
                for py_file in sorted(tools_dir.rglob('*.py')):
                    if self.should_ignore(py_file):
                        continue
                    rel_path = py_file.relative_to(self.root)
                    f.write(f"### {rel_path} (COMPLETE)\n")
                    f.write("```python\n")
                    f.write(self.read_file_safely(py_file))  # NO limit
                    f.write("\n```\n\n---\n\n")

            # COMPLETE Authentication
            f.write("## 🔐 AUTHENTICATION SYSTEM (COMPLETE)\n\n")
            
            auth_dir = self.root / 'user_auth'
            if auth_dir.exists():
                for py_file in sorted(auth_dir.rglob('*.py')):
                    if self.should_ignore(py_file):
                        continue
                    rel_path = py_file.relative_to(self.root)
                    f.write(f"### {rel_path} (COMPLETE)\n")
                    f.write("```python\n")
                    f.write(self.read_file_safely(py_file))  # NO limit
                    f.write("\n```\n\n---\n\n")

            # COMPLETE Workflows
            f.write("## 🔄 WORKFLOWS (COMPLETE)\n\n")
            
            workflows_dir = self.root / 'workflows'
            if workflows_dir.exists():
                for py_file in sorted(workflows_dir.rglob('*.py')):
                    if self.should_ignore(py_file):
                        continue
                    rel_path = py_file.relative_to(self.root)
                    f.write(f"### {rel_path} (COMPLETE)\n")
                    f.write("```python\n")
                    f.write(self.read_file_safely(py_file))  # NO limit
                    f.write("\n```\n\n---\n\n")

            # COMPLETE Utils
            f.write("## 🔧 UTILITIES (COMPLETE)\n\n")
            
            utils_dir = self.root / 'utils'
            if utils_dir.exists():
                for py_file in sorted(utils_dir.rglob('*.py')):
                    if self.should_ignore(py_file):
                        continue
                    rel_path = py_file.relative_to(self.root)
                    f.write(f"### {rel_path} (COMPLETE)\n")
                    f.write("```python\n")
                    f.write(self.read_file_safely(py_file))  # NO limit
                    f.write("\n```\n\n---\n\n")

            # Documentation
            f.write("## 📚 DOCUMENTATION (COMPLETE)\n\n")
            
            doc_files = ['README.md', 'QUICK_START.md', 'DEPLOYMENT_GUIDE.md', 'EASY_HOSTING.md']
            for doc_file in doc_files:
                file_path = self.root / doc_file
                if file_path.exists():
                    f.write(f"### {doc_file} (COMPLETE)\n")
                    f.write("```markdown\n")
                    f.write(self.read_file_safely(file_path))  # NO limit
                    f.write("\n```\n\n---\n\n")

            # Current Issues (from logs)
            f.write("## ⚠️ CURRENT ISSUES & CONTEXT\n\n")
            f.write("""Based on recent logs, there are two main issues to address:

### 1. Port Binding Error
```
OSError: [Errno 10048] error while attempting to bind on address ('::1', 8501, 0, 0): 
only one usage of each socket address (protocol/network address/port) is normally permitted
```
**Solution**: The application is trying to bind to port 8501 which is already in use.

### 2. Configuration Error
```
AttributeError: 'Config' object has no attribute 'GENERAL_SYSTEM_PROMPT'
```
**Solution**: The config.py file is missing the GENERAL_SYSTEM_PROMPT attribute that the agent_loop.py expects.

---

""")

            # Metadata
            f.write("## 📊 CODEBASE METRICS\n\n")
            f.write(f"- **Total Python Files**: {len(structure['python_modules'])}\n")
            f.write(f"- **Total Lines of Code**: {structure['total_lines']:,}\n")
            f.write(f"- **Main Categories**: {len([c for c, files in structure['files_by_category'].items() if files])}\n")
            f.write(f"- **External Dependencies**: ~{len(self.read_file_safely(self.root / 'requirements.txt').splitlines()) if (self.root / 'requirements.txt').exists() else 0}\n\n")

            f.write("---\n\n")
            f.write("**🎯 This COMPLETE export includes the full content of all major code files, optimized for LLM consumption with maximum context and understanding capability.**\n")

        print(f"✅ FULL Export complete! Generated: {self.output_file}")
        print(f"📊 Processed {structure['total_files']} files, {structure['total_lines']:,} lines of Python code")

def main():
    exporter = LLMCodebaseExporter()
    exporter.generate_export()

if __name__ == '__main__':
    main() 