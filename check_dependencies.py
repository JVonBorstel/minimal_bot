# check_dependencies.py
import importlib
import sys
import pkg_resources # To check versions (optional but good)

# --- Define a list of top-level modules to check based on requirements.txt ---
# This list is an *educated guess* of the primary importable module name for each requirement.
# Some packages install under a different name than the pip package name (e.g., PyYAML -> yaml).
# Some packages are namespaces or don't have a single top-level import.
# This list will need refinement based on actual usage in your project.

MODULES_TO_CHECK = {
    # Core Python Dependencies
    "dotenv": "python-dotenv",
    "dateutil": "python-dateutil",
    "packaging": "packaging",
    "typing_extensions": "typing_extensions",
    "pydantic": "pydantic",
    # "pydantic_core": "pydantic_core", # pydantic_core is usually a compiled extension

    # Database & ORM
    "sqlalchemy": "sqlalchemy",
    "alembic": "alembic",

    # Microsoft Bot Framework
    "botbuilder.core": "botbuilder-core",
    "botbuilder.schema": "botbuilder-schema",
    "botbuilder.integration.aiohttp": "botbuilder-integration-aiohttp",
    "botbuilder.dialogs": "botbuilder-dialogs",
    "botbuilder.ai": "botbuilder-ai", # May contain submodules like LUIS
    "botframework.connector": "botframework-connector",
    "botframework.streaming": "botframework-streaming",

    # Azure Services
    "azure.core": "azure-core",
    "azure.common": "azure-common",
    "azure.cognitiveservices.language.luis": "azure-cognitiveservices-language-luis",
    "azure.ai.contentsafety": "azure-ai-contentsafety",
    "msal": "msal",
    "msrest": "msrest",
    # "msrestazure": "msrestazure", # Often used via msrest
    "adal": "adal",

    # Web Server & HTTP
    "aiohttp": "aiohttp",
    "aiosignal": "aiosignal", # Dependency of aiohttp
    "aiohappyeyeballs": "aiohappyeyeballs", # Dependency
    "httpx": "httpx",
    "httpcore": "httpcore", # Dependency of httpx
    "httplib2": "httplib2",
    "requests": "requests",
    "requests_oauthlib": "requests-oauthlib",
    "requests_toolbelt": "requests-toolbelt",
    "websockets": "websockets",

    # AI/ML & LLM APIs
    "google.generativeai": "google-generativeai", # CRITICAL
    "google.ai.generativelanguage": "google-ai-generativelanguage", # CRITICAL
    "google.api_core": "google-api-core",
    "googleapiclient": "google-api-python-client", # googleapiclient.discovery
    "google.auth": "google-auth",
    # "google_auth_httplib2": "google-auth-httplib2", # Usually used via google.auth
    "google.cloud.aiplatform": "google-cloud-aiplatform",
    "google.cloud.bigquery": "google-cloud-bigquery",
    "google.cloud.storage": "google-cloud-storage",
    "google.cloud.resourcemanager": "google-cloud-resource-manager",
    # "google_genai": "google-genai", # This seems to be a duplicate pip name for google.generativeai
    "openai": "openai",
    "sentence_transformers": "sentence-transformers",
    "transformers": "transformers",
    "torch": "torch",
    "tokenizers": "tokenizers",
    "tiktoken": "tiktoken",
    "huggingface_hub": "huggingface-hub",

    # API Integration
    "jira": "jira",
    "github": "PyGithub", # Module is 'github'

    # Redis Support
    "redis": "redis",
    "fakeredis": "fakeredis",

    # Data Processing & ML
    "pandas": "pandas",
    "numpy": "numpy",
    "scipy": "scipy",
    "sklearn": "scikit-learn", # Module is 'sklearn'
    "matplotlib": "matplotlib",
    "seaborn": "seaborn",
    "nltk": "nltk",

    # JSON & Data Serialization
    "orjson": "orjson",
    "jsonschema": "jsonschema",
    # "jsonschema_specifications": "jsonschema-specifications", # Used by jsonschema
    "jsonpickle": "jsonpickle",
    "dataclasses_json": "dataclasses-json",
    "marshmallow": "marshmallow",

    # Async & Performance
    "aiofiles": "aiofiles",
    # "uvloop": "uvloop", # Platform specific

    # Utilities
    "rich": "rich",
    "click": "click",
    "tqdm": "tqdm",
    "tenacity": "tenacity",
    "cachetools": "cachetools",
    "multipart": "python-multipart", # Module is 'multipart'
    "filelock": "filelock",

    # Security & Crypto
    "cryptography": "cryptography",
    "jwt": "PyJWT", # Module is 'jwt'
    "nacl": "PyNaCl", # Module is 'nacl'
    "oauthlib": "oauthlib",
    "certifi": "certifi",

    # Development & Testing (usually not runtime dependencies for deployment)
    # "pytest": "pytest",
    # "mypy": "mypy",
    # "flake8": "flake8",
    # "pylint": "pylint",
    # "coverage": "coverage",
    # "black": "black",
    # "isort": "isort",

    # Configuration & Environment
    "yaml": "PyYAML", # Module is 'yaml'
    "toml": "toml",
    "configparser": "configparser",

    # Logging & Monitoring
    "structlog": "structlog",
    "colorama": "colorama",

    # Bot Framework Text Recognition
    "recognizers_text": "recognizers-text",
    "recognizers_text.choice": "recognizers-text-choice",
    "recognizers_text.datetime": "recognizers-text-date-time",
    "recognizers_text.number": "recognizers-text-number",
    "recognizers_text.numberwithunit": "recognizers-text-number-with-unit",
    "teams.ai": "teams-ai",


    # Core Support Libraries (many of these are dependencies of others)
    "six": "six",
    "altair": "altair",
    # "annotated_types": "annotated-types", # Pydantic dep
    "anyio": "anyio",
    # "astroid": "astroid", # Pylint dep
    "attrs": "attrs",
    "babel": "Babel",
    "blinker": "blinker",
    # "cffi": "cffi", # Cryptography dep
    "charset_normalizer": "charset-normalizer", # Requests dep
    # "contourpy": "contourpy", # Matplotlib dep
    "cycler": "cycler", # Matplotlib dep
    "datedelta": "datedelta",
    "defusedxml": "defusedxml",
    "deprecated": "Deprecated",
    "dill": "dill",
    "distro": "distro",
    "dns": "dnspython", # email_validator dep, module is 'dns'
    "docstring_parser": "docstring_parser",
    "email_validator": "email_validator",
    "emoji": "emoji",
    "fontTools": "fonttools", # Matplotlib dep
    "frozenlist": "frozenlist", # aiohttp dep
    "fsspec": "fsspec", # pandas, huggingface_hub dep
    "git": "GitPython", # Module is 'git'
    # "google_crc32c": "google-crc32c", # google-cloud-storage dep
    # "google_resumable_media": "google-resumable-media", # google-cloud-storage dep
    "google.protobuf": "protobuf", # Many google libs dep
    "grapheme": "grapheme",
    # "grpc": "grpcio", # Many google libs dep
    # "h11": "h11", # httpcore dep
    "idna": "idna", # Requests dep
    # "iniconfig": "iniconfig", # pytest dep
    "isodate": "isodate", # msrest dep
    "jinja2": "Jinja2",
    "jiter": "jiter", # orjson dep
    "joblib": "joblib", # scikit-learn dep
    "kiwisolver": "kiwisolver", # Matplotlib dep
    "markupsafe": "MarkupSafe", # Jinja2 dep
    # "mccabe": "mccabe", # Flake8 dep
    "mpmath": "mpmath", # Sympy dep
    "multidict": "multidict", # aiohttp dep
    "multipledispatch": "multipledispatch", # Numba/others
    "narwhals": "narwhals", # Polars/Pandas interop
    "networkx": "networkx",
    "PIL": "pillow", # Module is 'PIL'
    "platformdirs": "platformdirs",
    # "pluggy": "pluggy", # pytest dep
    "propcache": "propcache", # streamlit dep
    # "proto_plus": "proto-plus", # google-cloud libs dep
    "pyarrow": "pyarrow", # pandas dep
    "pyasn1": "pyasn1", # google-auth dep
    # "pyasn1_modules": "pyasn1_modules", # google-auth dep
    # "pycodestyle": "pycodestyle", # Flake8 dep
    "pycparser": "pycparser", # cffi dep
    "pydeck": "pydeck", # streamlit dep
    # "pyflakes": "pyflakes", # Flake8 dep
    "pyparsing": "pyparsing", # Matplotlib, packaging dep
    "pytz": "pytz", # pandas dep
    "referencing": "referencing", # jsonschema dep
    "regex": "regex",
    "rpds": "rpds-py", # jsonschema dep
    "rsa": "rsa", # google-auth dep
    "safetensors": "safetensors", # transformers dep
    "shapely": "shapely",
    # "smmap": "smmap", # gitpython dep
    "sniffio": "sniffio", # anyio, httpcore dep
    "streamlit": "streamlit",
    "sympy": "sympy",
    "tabulate": "tabulate",
    "threadpoolctl": "threadpoolctl", # scikit-learn, scipy dep
    "tomli": "tomli", # pytest, black dep
    "tomlkit": "tomlkit", # poetry, other build tools
    "tornado": "tornado", # streamlit dep
    # "types_PyYAML": "types-PyYAML", # Typing stub
    # "types_requests": "types-requests", # Typing stub
    "typing_inspect": "typing-inspect",
    # "typing_inspection": "typing-inspection", # Seems like an alternative to typing_inspect
    "tzdata": "tzdata", # pytz dep
    "uritemplate": "uritemplate", # google-api-python-client dep
    "urllib3": "urllib3", # requests dep
    "vulture": "vulture", # Dead code finder
    "watchdog": "watchdog",
    "wrapt": "wrapt", # Deprecated dep
    "yarl": "yarl", # aiohttp dep
}

# Platform specific modules
if sys.platform != "win32":
    MODULES_TO_CHECK["uvloop"] = "uvloop"


def check_dependencies():
    print("--- Starting Dependency Import Check ---")
    successful_imports = []
    failed_imports = []
    missing_but_optional = [] # For modules that might not be installed based on platform

    critical_gemini_sdk = "google.generativeai"
    gemini_sdk_found = False

    for module_name, package_name in MODULES_TO_CHECK.items():
        try:
            importlib.import_module(module_name)
            version = "N/A"
            try:
                # Attempt to get version, some modules might not have __version__
                # or might be installed differently (e.g. namespace packages)
                # Using pkg_resources is more reliable if the package is installed via pip
                dist = pkg_resources.get_distribution(package_name)
                version = dist.version
            except pkg_resources.DistributionNotFound:
                # Fallback for modules where package name differs or complex cases
                try:
                    mod = sys.modules[module_name]
                    version = getattr(mod, '__version__', 'unknown')
                except (KeyError, AttributeError):
                    version = 'unknown (could not fetch)'
            except Exception:
                version = 'error fetching version'

            print(f"[ OK ] Imported: {module_name:<40} (from package: {package_name}, version: {version})")
            successful_imports.append(module_name)
            if module_name == critical_gemini_sdk:
                gemini_sdk_found = True
        except ImportError as e:
            # Check if it's a platform-specific issue we can ignore
            if package_name == "uvloop" and sys.platform == "win32":
                print(f"[INFO] Skipped: {module_name:<40} (uvloop is not for Windows)")
                missing_but_optional.append(f"{module_name} (not for Windows)")
            else:
                print(f"[FAIL] FAILED to import: {module_name:<35} (expected from package: {package_name}) - Error: {e}")
                failed_imports.append(module_name)
        except Exception as e:
            print(f"[ERROR] UNEXPECTED ERROR importing: {module_name:<30} (from package: {package_name}) - Error: {e}")
            failed_imports.append(module_name)


    print("\n--- Dependency Check Summary ---")
    print(f"Total modules checked: {len(MODULES_TO_CHECK)}")
    print(f"Successfully imported: {len(successful_imports)}")
    print(f"Failed imports: {len(failed_imports)}")
    if missing_but_optional:
        print(f"Skipped (optional/platform-specific): {len(missing_but_optional)}")

    if critical_gemini_sdk:
        if gemini_sdk_found:
            print(f"\n[CRITICAL CHECK - PASS] Gemini SDK ('{critical_gemini_sdk}') imported successfully.")
        else:
            print(f"\n[CRITICAL CHECK - FAIL] Gemini SDK ('{critical_gemini_sdk}') FAILED TO IMPORT. LLM functionality will be broken.")
            if critical_gemini_sdk not in failed_imports: # Should be if import failed
                 failed_imports.append(f"{critical_gemini_sdk} - CRITICAL")


    if failed_imports:
        print("\n[ACTION REQUIRED] The following modules failed to import:")
        for failed_module in failed_imports:
            print(f"  - {failed_module}")
        print("\nPlease ensure all dependencies from requirements.txt are installed correctly in your virtual environment.")
        print("Try running: pip install --upgrade -r requirements.txt")
        return False
    else:
        print("\n[SUCCESS] All specified modules imported successfully!")
        return True

if __name__ == "__main__":
    if check_dependencies():
        print("\nDependency check passed. Environment looks good for basic imports.")
        sys.exit(0)
    else:
        print("\nDependency check failed. Please address the import errors.")
        sys.exit(1)