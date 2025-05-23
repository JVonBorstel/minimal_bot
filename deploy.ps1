# 🚀 Minimal Bot Quick Deployment Script (PowerShell)

param(
    [string]$Method = ""
)

# Colors for output
$ErrorActionPreference = "Stop"

function Write-Status {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Blue
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

Write-Host "🤖 Minimal Bot Deployment Script (Windows)" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# Check prerequisites
function Test-Prerequisites {
    Write-Status "Checking prerequisites..."
    
    # Check if .env exists
    if (-not (Test-Path ".env")) {
        Write-Error ".env file not found!"
        Write-Host "Please create a .env file with your API keys and configuration."
        Write-Host "Required variables:"
        Write-Host "  - MICROSOFT_APP_ID"
        Write-Host "  - MICROSOFT_APP_PASSWORD"
        Write-Host "  - GEMINI_API_KEY"
        Write-Host "  - JIRA_API_URL, JIRA_API_EMAIL, JIRA_API_TOKEN"
        Write-Host "  - GITHUB_TOKEN"
        exit 1
    }
    
    # Check if Docker is available
    $global:DockerAvailable = $false
    try {
        docker --version | Out-Null
        Write-Success "Docker found"
        $global:DockerAvailable = $true
    }
    catch {
        Write-Warning "Docker not found - will use Python deployment"
        $global:DockerAvailable = $false
    }
    
    # Check if Python is available
    $global:PythonAvailable = $false
    try {
        python --version | Out-Null
        Write-Success "Python found"
        $global:PythonAvailable = $true
    }
    catch {
        Write-Error "Python not found!"
        exit 1
    }
}

# Run tests before deployment
function Invoke-Tests {
    Write-Status "Running pre-deployment tests..."
    
    if ($global:PythonAvailable) {
        Write-Status "Running basic startup test..."
        $result = python tests\debug\test_basic_startup.py
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Basic startup test passed"
        } else {
            Write-Error "Basic startup test failed"
            exit 1
        }
        
        Write-Status "Running onboarding system test..."
        $result = python tests\scenarios\test_onboarding_system.py
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Onboarding system test passed"
        } else {
            Write-Error "Onboarding system test failed"
            exit 1
        }
    }
}

# Docker deployment
function Deploy-WithDocker {
    Write-Status "Deploying with Docker..."
    
    # Build and start
    docker-compose up -d --build
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Docker deployment failed"
        exit 1
    }
    
    # Wait for startup
    Write-Status "Waiting for bot to start..."
    Start-Sleep -Seconds 10
    
    # Health check
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:3978/healthz" -Method Get -TimeoutSec 10
        Write-Success "Bot is healthy and running on port 3978!"
        Write-Success "Health status: $($response.overall_status)"
    }
    catch {
        Write-Error "Health check failed"
        Write-Host "Check logs with: docker-compose logs minimal-bot"
        exit 1
    }
}

# Python deployment
function Deploy-WithPython {
    Write-Status "Deploying with Python..."
    
    # Install dependencies
    Write-Status "Installing dependencies..."
    pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to install dependencies"
        exit 1
    }
    
    # Start bot
    Write-Status "Starting bot..."
    $job = Start-Job -ScriptBlock {
        Set-Location $using:PWD
        python app.py
    }
    
    # Save job info
    $job.Id | Out-File -FilePath "bot.pid" -Encoding ASCII
    
    # Wait for startup
    Write-Status "Waiting for bot to start..."
    Start-Sleep -Seconds 8
    
    # Health check
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:3978/healthz" -Method Get -TimeoutSec 10
        Write-Success "Bot is healthy and running on port 3978! (Job ID: $($job.Id))"
        Write-Success "Health status: $($response.overall_status)"
        Write-Status "Monitor logs: Receive-Job -Id $($job.Id) -Keep"
        Write-Status "Stop bot: Stop-Job -Id $($job.Id); Remove-Job -Id $($job.Id)"
    }
    catch {
        Write-Error "Health check failed"
        Write-Host "Stop the job: Stop-Job -Id $($job.Id); Remove-Job -Id $($job.Id)"
        Stop-Job -Id $job.Id
        Remove-Job -Id $job.Id
        exit 1
    }
}

# Main deployment flow
function Start-Deployment {
    Write-Host ""
    Write-Host "🚀 Starting deployment process..." -ForegroundColor Cyan
    Write-Host ""
    
    Test-Prerequisites
    Invoke-Tests
    
    Write-Host ""
    Write-Host "Choose deployment method:"
    Write-Host "1. Docker (recommended)"
    Write-Host "2. Python (direct)"
    Write-Host ""
    
    $choice = $Method
    if (-not $choice) {
        if ($global:DockerAvailable) {
            $choice = Read-Host "Enter choice (1 or 2) [default: 1]"
            if (-not $choice) { $choice = "1" }
        } else {
            $choice = "2"
            Write-Warning "Docker not available, using Python deployment"
        }
    }
    
    switch ($choice) {
        "1" {
            if ($global:DockerAvailable) {
                Deploy-WithDocker
            } else {
                Write-Error "Docker not available!"
                exit 1
            }
        }
        "2" {
            Deploy-WithPython
        }
        default {
            Write-Error "Invalid choice"
            exit 1
        }
    }
    
    Write-Host ""
    Write-Success "🎉 Deployment complete!" 
    Write-Host ""
    Write-Host "📊 Next steps:" -ForegroundColor Cyan
    Write-Host "1. Test the bot: Invoke-RestMethod -Uri http://localhost:3978/healthz"
    Write-Host "2. Update your Bot Framework registration messaging endpoint"
    Write-Host "3. Monitor logs for any issues"
    Write-Host "4. See DEPLOYMENT_GUIDE.md for integration with your team bot"
    Write-Host ""
}

# Run main function
try {
    Start-Deployment
}
catch {
    Write-Error "Deployment failed: $($_.Exception.Message)"
    exit 1
} 