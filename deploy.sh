#!/bin/bash

# 🚀 Minimal Bot Quick Deployment Script

set -e  # Exit on any error

echo "🤖 Minimal Bot Deployment Script"
echo "================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check if .env exists
    if [ ! -f ".env" ]; then
        print_error ".env file not found!"
        echo "Please create a .env file with your API keys and configuration."
        echo "Required variables:"
        echo "  - MICROSOFT_APP_ID"
        echo "  - MICROSOFT_APP_PASSWORD" 
        echo "  - GEMINI_API_KEY"
        echo "  - JIRA_API_URL, JIRA_API_EMAIL, JIRA_API_TOKEN"
        echo "  - GITHUB_TOKEN"
        exit 1
    fi
    
    # Check if Docker is available
    if command -v docker &> /dev/null; then
        print_success "Docker found"
        DOCKER_AVAILABLE=true
    else
        print_warning "Docker not found - will use Python deployment"
        DOCKER_AVAILABLE=false
    fi
    
    # Check if Python is available
    if command -v python &> /dev/null || command -v python3 &> /dev/null; then
        print_success "Python found"
        PYTHON_AVAILABLE=true
    else
        print_error "Python not found!"
        exit 1
    fi
}

# Run tests before deployment
run_tests() {
    print_status "Running pre-deployment tests..."
    
    if [ "$PYTHON_AVAILABLE" = true ]; then
        python tests/debug/test_basic_startup.py
        if [ $? -eq 0 ]; then
            print_success "Basic startup test passed"
        else
            print_error "Basic startup test failed"
            exit 1
        fi
        
        python tests/scenarios/test_onboarding_system.py
        if [ $? -eq 0 ]; then
            print_success "Onboarding system test passed"
        else
            print_error "Onboarding system test failed"
            exit 1
        fi
    fi
}

# Docker deployment
deploy_with_docker() {
    print_status "Deploying with Docker..."
    
    # Build and start
    docker-compose up -d --build
    
    # Wait for startup
    print_status "Waiting for bot to start..."
    sleep 10
    
    # Health check
    if curl -f http://localhost:3978/healthz > /dev/null 2>&1; then
        print_success "Bot is healthy and running on port 3978!"
    else
        print_error "Health check failed"
        echo "Check logs with: docker-compose logs minimal-bot"
        exit 1
    fi
}

# Python deployment
deploy_with_python() {
    print_status "Deploying with Python..."
    
    # Install dependencies
    pip install -r requirements.txt
    
    # Start bot in background
    nohup python app.py > bot.log 2>&1 &
    BOT_PID=$!
    echo $BOT_PID > bot.pid
    
    # Wait for startup
    print_status "Waiting for bot to start..."
    sleep 5
    
    # Health check
    if curl -f http://localhost:3978/healthz > /dev/null 2>&1; then
        print_success "Bot is healthy and running on port 3978! (PID: $BOT_PID)"
        print_status "Logs: tail -f bot.log"
        print_status "Stop: kill $BOT_PID"
    else
        print_error "Health check failed"
        echo "Check logs: tail bot.log"
        exit 1
    fi
}

# Main deployment flow
main() {
    echo ""
    echo "🚀 Starting deployment process..."
    echo ""
    
    check_prerequisites
    run_tests
    
    echo ""
    echo "Choose deployment method:"
    echo "1. Docker (recommended)"
    echo "2. Python (direct)"
    echo ""
    
    if [ "$DOCKER_AVAILABLE" = true ]; then
        read -p "Enter choice (1 or 2) [default: 1]: " choice
        choice=${choice:-1}
    else
        choice=2
        print_warning "Docker not available, using Python deployment"
    fi
    
    case $choice in
        1)
            if [ "$DOCKER_AVAILABLE" = true ]; then
                deploy_with_docker
            else
                print_error "Docker not available!"
                exit 1
            fi
            ;;
        2)
            deploy_with_python
            ;;
        *)
            print_error "Invalid choice"
            exit 1
            ;;
    esac
    
    echo ""
    print_success "🎉 Deployment complete!"
    echo ""
    echo "📊 Next steps:"
    echo "1. Test the bot: curl http://localhost:3978/healthz"
    echo "2. Update your Bot Framework registration messaging endpoint"
    echo "3. Monitor logs for any issues"
    echo "4. See DEPLOYMENT_GUIDE.md for integration with your team bot"
    echo ""
}

# Run main function
main "$@" 