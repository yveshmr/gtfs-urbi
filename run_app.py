import subprocess
import os
import time
import sys
import webbrowser
import socket

# ============================================================
# CONFIG
# ============================================================

ROOT = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(ROOT, "frontend")
NPM_CMD = r"C:\Program Files\nodejs\npm.cmd"


# ============================================================
# SINGLE INSTANCE (impede loop)
# ============================================================

def single_instance_check():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 65432))
    except OSError:
        print("⚠️ Aplicação já está em execução.")
        sys.exit(0)


# ============================================================
# DEPENDÊNCIAS
# ============================================================

def check_dependencies():
    if not os.path.exists(NPM_CMD):
        print("❌ Node.js não encontrado.")
        sys.exit(1)

    subprocess.run(f'"{NPM_CMD}" --version', shell=True, check=True)


# ============================================================
# BACKEND (SEM RELOAD!)
# ============================================================

def start_backend():
    print("🚀 Iniciando backend...")

    python_cmd = sys.executable

    return subprocess.Popen(
        f'"{python_cmd}" -m uvicorn app.main:app',
        cwd=ROOT,
        shell=True,
    )


# ============================================================
# FRONTEND
# ============================================================

def start_frontend():
    print("🎨 Iniciando frontend...")

    return subprocess.Popen(
        f'"{NPM_CMD}" run dev',
        cwd=FRONTEND_DIR,
        shell=True,
    )


# ============================================================
# BROWSER
# ============================================================

def open_browser():
    time.sleep(5)
    webbrowser.open("http://localhost:5173")


# ============================================================
# MAIN
# ============================================================

def main():
    single_instance_check()
    check_dependencies()

    backend = start_backend()
    time.sleep(6)

    frontend = start_frontend()
    open_browser()

    backend.wait()
    frontend.wait()


if __name__ == "__main__":
    main()