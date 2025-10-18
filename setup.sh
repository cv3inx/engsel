#!/usr/bin/env bash
clear
set -e
set -o pipefail

VENV_DIR="venv"
LOG_FILE="install.log"

RESET='\033[0m'
BOLD='\033[1m'
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD_GREEN='\033[1;32m'

log_info() { echo -e "${RESET}[i] $1${RESET}"; }
log_success() { echo -e "${GREEN}[+] $1${RESET}"; }
log_warn() { echo -e "${YELLOW}[!] $1${RESET}"; }
log_error() { echo -e "${RED}[x] Error: $1${RESET}" >&2; }
print_header() { echo -e "\n${BOLD}--- $1 ---${RESET}"; }

run_with_spinner() {
    local cmd="$1"
    local msg="$2"
    local spin='|/-\'
    local i=0
    tput civis
    eval "$cmd" >> "$LOG_FILE" 2>&1 &
    local pid=$!
    echo -n "  "
    while kill -0 $pid 2>/dev/null; do
        i=$(( (i+1) %4 ))
        echo -ne "${CYAN}\r[${spin:$i:1}]${RESET} $msg"
        sleep 0.1
    done
    tput cnorm
    echo -ne "\r$(printf '%*s' $((${#msg}+5)))\r"
    wait $pid
    return $?
}

print_usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Script universal untuk setup environment Python di Linux dan Termux."
    echo ""
    echo "Options:"
    echo "  --no-venv    Install paket secara global (bukan di venv). Di Termux, ini"
    echo "               adalah default dan flag ini diabaikan."
    echo "  -h, --help   Tampilkan pesan bantuan ini."
}

cleanup() {
    tput cnorm
    if [ $? -ne 0 ]; then
        log_error "Instalasi gagal. Periksa '$LOG_FILE' untuk detail."
    fi
}
trap cleanup EXIT INT


echo "Installation Log - $(date)" > "$LOG_FILE"
echo "=======================================" >> "$LOG_FILE"

USE_VENV=true
IS_TERMUX=false

if [[ "$PREFIX" == *"/com.termux"* ]]; then
    IS_TERMUX=true
    USE_VENV=false
fi

for arg in "$@"; do
    case $arg in
        --no-venv)
        [ "$IS_TERMUX" = false ] && USE_VENV=false
        shift
        ;;
        -h|--help)
        print_usage
        exit 0
        ;;
    esac
done

echo -e "${BOLD}=======================================${RESET}"
echo -e "${BOLD}            Anomali Engsel           ${RESET}"
echo -e "${BOLD}=======================================${RESET}"
echo
log_info "Log detail akan disimpan di: $LOG_FILE"

print_header "1. Mendeteksi Lingkungan Sistem"

SUDO_CMD=""
PYTHON_PKG="python3"
PIP_PKG="python3-pip"
VENV_PKG="python3-venv"
PYTHON_CMD="python3"
PIP_CMD="pip3"
PKG_INSTALL_CMD=""
PKG_UPDATE_CMD=""

if $IS_TERMUX; then
    log_success "Deteksi Termux"
    PKG_UPDATE_CMD="pkg update -y"
    PKG_INSTALL_CMD="pkg install -y"
    PYTHON_PKG="python"
    PIP_PKG="python-pip"
    VENV_PKG=""
    PYTHON_CMD="python"
    PIP_CMD="pip"

elif command -v apt >/dev/null 2>&1; then
    log_success "Deteksi apt (Debian/Ubuntu)"
    SUDO_CMD="sudo"
    PKG_UPDATE_CMD="sudo apt update -y"
    PKG_INSTALL_CMD="sudo apt install -y"

elif command -v dnf >/dev/null 2>&1; then
    log_success "Deteksi dnf (Fedora/RHEL)"
    SUDO_CMD="sudo"
    PKG_INSTALL_CMD="sudo dnf install -y"
    VENV_PKG=""

elif command -v pacman >/dev/null 2>&1; then
    log_success "Deteksi pacman (Arch Linux)"
    SUDO_CMD="sudo"
    PKG_UPDATE_CMD="sudo pacman -Syu --noconfirm"
    PKG_INSTALL_CMD="sudo pacman -S --noconfirm"
    PYTHON_PKG="python"
    PIP_PKG="python-pip"
    VENV_PKG=""
    PYTHON_CMD="python"
    PIP_CMD="pip"
else
    log_error "Manajer paket tidak didukung."
    exit 1
fi

print_header "2. Instalasi Kebutuhan Sistem"

if [ -n "$PKG_UPDATE_CMD" ]; then
    if ! run_with_spinner "$PKG_UPDATE_CMD" "Updating system packages..."; then
        log_error "Update paket gagal."
        exit 1
    fi
    log_success "Paket sistem telah diupdate"
fi

INSTALL_CMD="$SUDO_CMD $PKG_INSTALL_CMD $PYTHON_PKG $PIP_PKG $VENV_PKG"
if ! run_with_spinner "$INSTALL_CMD" "Installing Python, Pip, & Venv..."; then
    log_error "Instalasi Python gagal."
    exit 1
fi
log_success "Kebutuhan dasar Python terinstal"

print_header "3. Instalasi Paket Python"

if [ ! -f "requirements.txt" ]; then
    log_error "file 'requirements.txt' tidak ditemukan."
    exit 1
fi

if [ "$USE_VENV" = true ] && [ "$IS_TERMUX" = false ]; then
    log_info "Menggunakan venv (pilihan terbaik untuk Linux)."
    
    if [ ! -d "$VENV_DIR" ]; then
        if ! run_with_spinner "$PYTHON_CMD -m venv $VENV_DIR" "Membuat virtual environment..."; then
            log_error "Gagal membuat venv."
            exit 1
        fi
        log_success "Virtual environment dibuat di './$VENV_DIR'"
    else
        log_info "Direktori '$VENV_DIR' sudah ada, menggunakan yang ada."
    fi
    
    VENV_PIP_CMD="'./$VENV_DIR/bin/pip' install -r requirements.txt"
    if ! run_with_spinner "$VENV_PIP_CMD" "Menginstal paket ke venv..."; then
        log_error "Instalasi pip gagal."
        exit 1
    fi
    
    echo -e "${GREEN}--------------------------------------------------------${RESET}"
    log_success "Paket telah terinstal di dalam '$VENV_DIR'."
    echo -e "${BOLD}> Untuk mengaktifkan lingkungan ini, jalankan:${RESET}"
    echo -e "   ${BOLD_GREEN}source $VENV_DIR/bin/activate${RESET}"
    echo -e "${BOLD}> Lalu jalankan:${RESET}"
    echo -e "   ${BOLD_GREEN}${PYTHON_CMD} main.py${RESET}"
    echo -e "${GREEN}--------------------------------------------------------${RESET}"

else
    if $IS_TERMUX; then
        log_info "Termux: Menginstal paket dari requirements.txt..."
    else
        log_warn "Linux: Menginstal paket secara global (sesuai flag --no-venv)."
    fi

    GLOBAL_PIP_CMD="$SUDO_CMD $PIP_CMD install -r requirements.txt"
    if ! run_with_spinner "$GLOBAL_PIP_CMD" "Menginstal requirements.txt..."; then
        log_error "Instalasi pip gagal."
        exit 1
    fi
    
    echo -e "${GREEN}--------------------------------------------------------${RESET}"
    log_success "Paket Python telah terinstal."
    echo -e "${BOLD}> Untuk menjalankan program, ketik:${RESET}"
    echo -e "   ${BOLD_GREEN}${PYTHON_CMD} main.py${RESET}"
    echo -e "${GREEN}--------------------------------------------------------${RESET}"
fi


