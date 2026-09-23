import socket
import threading
import hashlib
import time
import tkinter as tk
from tkinter import ttk, messagebox

# --- Palette inspirée de WhatsApp ---
COULEUR_ENTETE      = "#075E54"
COULEUR_FOND_CHAT   = "#ECE5DD"
COULEUR_BULLE_MOI   = "#DCF8C6"
COULEUR_BULLE_AUTRE = "#FFFFFF"
COULEUR_ACCENT      = "#25D366"
COULEUR_TEXTE_SYS   = "#7A8B99"

# Couleurs utilisées pour les avatars (une couleur stable par pseudo)
PALETTE_AVATARS = [
    "#F44336", "#E91E63", "#9C27B0", "#673AB7",
    "#3F51B5", "#2196F3", "#009688", "#FF9800",
    "#795548", "#607D8B",
]


def couleur_pour_pseudo(pseudo):
    """Retourne toujours la même couleur pour un même pseudo (stable entre relances)."""
    h = int(hashlib.md5(pseudo.encode('utf-8')).hexdigest(), 16)
    return PALETTE_AVATARS[h % len(PALETTE_AVATARS)]


class ChatClientGUI:
    def __init__(self, master):
        self.master = master
        self.master.title("i-TAFA")
        self.master.geometry("420x600")
        self.master.minsize(340, 420)
        self.master.configure(bg=COULEUR_FOND_CHAT)

        self.client_socket = None
        self.username = ""

        self.afficher_ecran_connexion()

    # ------------------------------------------------------------------
    #  ÉCRAN DE CONNEXION : pseudo + adresse IP du serveur + port
    # ------------------------------------------------------------------
    def afficher_ecran_connexion(self):
        self.login_frame = tk.Frame(self.master, bg=COULEUR_FOND_CHAT)
        self.login_frame.pack(fill="both", expand=True)

        conteneur = tk.Frame(self.login_frame, bg="white", padx=30, pady=30)
        conteneur.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(conteneur, text="💬", font=("Segoe UI Emoji", 40), bg="white").pack(pady=(0, 10))
        tk.Label(conteneur, text="i-TAFA", font=("Segoe UI", 20, "bold"), fg="#075E54", bg="white").pack(pady=(0, 5))
        tk.Label(conteneur, text="Rejoindre le chat", font=("Segoe UI", 16, "bold"), bg="white").pack(pady=(0, 20))

        tk.Label(conteneur, text="Votre pseudo", font=("Segoe UI", 10), bg="white", anchor="w").pack(fill="x")
        self.entry_pseudo = tk.Entry(conteneur, font=("Segoe UI", 11))
        self.entry_pseudo.pack(fill="x", pady=(2, 12))

        tk.Label(conteneur, text="Adresse IP du serveur", font=("Segoe UI", 10), bg="white", anchor="w").pack(fill="x")
        self.entry_ip = tk.Entry(conteneur, font=("Segoe UI", 11))
        self.entry_ip.insert(0, "127.0.0.1")
        self.entry_ip.pack(fill="x", pady=(2, 12))

        tk.Label(conteneur, text="Port", font=("Segoe UI", 10), bg="white", anchor="w").pack(fill="x")
        self.entry_port = tk.Entry(conteneur, font=("Segoe UI", 11))
        self.entry_port.insert(0, "5000")
        self.entry_port.pack(fill="x", pady=(2, 20))

        tk.Label(
            conteneur,
            text="Astuce : pour discuter entre deux ordinateurs,\nutilisez l'adresse IP locale de la machine qui\nlance server.py (ex: 192.168.1.23), pas 127.0.0.1.",
            font=("Segoe UI", 8), fg="#888888", bg="white", justify="left"
        ).pack(fill="x", pady=(0, 15))

        btn = tk.Button(
            conteneur, text="Se connecter", font=("Segoe UI", 11, "bold"),
            bg=COULEUR_ACCENT, fg="white", activebackground="#1EBE5A",
            relief="flat", padx=10, pady=8, command=self.tenter_connexion
        )
        btn.pack(fill="x")
        self.entry_pseudo.focus_set()
        self.master.bind("<Return>", lambda e: self.tenter_connexion())

    def tenter_connexion(self):
        pseudo = self.entry_pseudo.get().strip()
        ip = self.entry_ip.get().strip()
        port_txt = self.entry_port.get().strip()

        if not pseudo:
            messagebox.showwarning("Pseudo manquant", "Merci de saisir un pseudo.")
            return
        if not ip:
            messagebox.showwarning("Adresse manquante", "Merci de saisir l'adresse IP du serveur.")
            return
        try:
            port = int(port_txt)
        except ValueError:
            messagebox.showwarning("Port invalide", "Le port doit être un nombre (ex: 5000).")
            return

        self.username = pseudo
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_socket.settimeout(5)
        try:
            self.client_socket.connect((ip, port))
            self.client_socket.settimeout(None)
            self.client_socket.send((self.username + "\n").encode('utf-8'))
        except Exception as e:
            messagebox.showerror(
                "Erreur de connexion",
                f"Impossible de se connecter à {ip}:{port}.\n\n"
                f"Vérifiez que server.py tourne bien sur cette machine,\n"
                f"que l'adresse IP est correcte, et que le pare-feu\n"
                f"autorise le port {port}.\n\nDétail : {e}"
            )
            self.client_socket = None
            return

        self.master.unbind("<Return>")
        self.login_frame.destroy()
        self.construire_interface_chat()

        self.listen_thread = threading.Thread(target=self.receive_messages, daemon=True)
        self.listen_thread.start()
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)

    # ------------------------------------------------------------------
    #  INTERFACE DE CHAT (bulles + avatars façon WhatsApp)
    # ------------------------------------------------------------------
    def construire_interface_chat(self):
        self.master.rowconfigure(1, weight=1)
        self.master.columnconfigure(0, weight=1)

        # --- Barre d'en-tête ---
        entete = tk.Frame(self.master, bg=COULEUR_ENTETE, height=56)
        entete.grid(row=0, column=0, sticky="ew")
        entete.grid_propagate(False)
        tk.Label(entete, text="👥  Salon de discussion", font=("Segoe UI", 13, "bold"),
                 bg=COULEUR_ENTETE, fg="white").pack(side="left", padx=15)
        tk.Label(entete, text=f"connecté en tant que {self.username}", font=("Segoe UI", 8),
                 bg=COULEUR_ENTETE, fg="#CFEFE8").pack(side="right", padx=15)

        # --- Zone de messages défilante (Canvas + Frame interne) ---
        zone_conteneur = tk.Frame(self.master, bg=COULEUR_FOND_CHAT)
        zone_conteneur.grid(row=1, column=0, sticky="nsew")
        zone_conteneur.rowconfigure(0, weight=1)
        zone_conteneur.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(zone_conteneur, bg=COULEUR_FOND_CHAT, highlightthickness=0)
        scrollbar = ttk.Scrollbar(zone_conteneur, orient="vertical", command=self.canvas.yview)
        self.messages_frame = tk.Frame(self.canvas, bg=COULEUR_FOND_CHAT)

        self.messages_frame.bind(
            "<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas_window = self.canvas.create_window((0, 0), window=self.messages_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))

        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        # Molette de la souris (Windows/Mac et Linux)
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))

        # --- Barre de saisie ---
        bas = tk.Frame(self.master, bg="#F0F0F0", height=56)
        bas.grid(row=2, column=0, sticky="ew")
        bas.columnconfigure(0, weight=1)

        self.entry_msg = tk.Entry(bas, font=("Segoe UI", 11), relief="flat")
        self.entry_msg.grid(row=0, column=0, sticky="ew", padx=(10, 5), pady=10, ipady=6)
        self.entry_msg.bind("<Return>", self.send_message)
        self.entry_msg.focus_set()

        self.btn_send = tk.Button(
            bas, text="Envoyer", font=("Segoe UI", 10, "bold"), bg=COULEUR_ACCENT, fg="white",
            activebackground="#1EBE5A", relief="flat", padx=14, command=self.send_message
        )
        self.btn_send.grid(row=0, column=1, padx=(0, 10), pady=10)

        self.add_system_message(f"Vous avez rejoint le chat en tant que {self.username}.")

    # ------------------------------------------------------------------
    #  AFFICHAGE DES MESSAGES (bulles + avatar)
    # ------------------------------------------------------------------
    def add_system_message(self, texte):
        """Message centré et discret, comme les notifications d'arrivée/départ sur WhatsApp."""
        ligne = tk.Frame(self.messages_frame, bg=COULEUR_FOND_CHAT)
        ligne.pack(fill="x", pady=6, padx=10)
        tk.Label(
            ligne, text=texte, font=("Segoe UI", 8, "italic"),
            bg="#D9E4EA", fg=COULEUR_TEXTE_SYS, padx=10, pady=4
        ).pack(anchor="center")
        self._scroll_vers_le_bas()

    def add_chat_message(self, pseudo, texte, est_moi):
        """Ajoute une bulle de message, avec avatar rond si ce n'est pas nous."""
        heure = time.strftime("%H:%M")
        ligne = tk.Frame(self.messages_frame, bg=COULEUR_FOND_CHAT)
        ligne.pack(fill="x", pady=3, padx=8, anchor="e" if est_moi else "w")

        bloc = tk.Frame(ligne, bg=COULEUR_FOND_CHAT)
        if est_moi:
            bloc.pack(anchor="e")
            bulle_col = 0
        else:
            # Avatar rond avec l'initiale du pseudo, coloré de façon stable
            couleur = couleur_pour_pseudo(pseudo)
            avatar = tk.Canvas(bloc, width=34, height=34, bg=COULEUR_FOND_CHAT, highlightthickness=0)
            avatar.grid(row=0, column=0, sticky="s", padx=(0, 6))
            avatar.create_oval(2, 2, 32, 32, fill=couleur, outline="")
            avatar.create_text(17, 17, text=pseudo[:1].upper(), fill="white", font=("Segoe UI", 12, "bold"))
            bloc.pack(anchor="w")
            bulle_col = 1

        couleur_bulle = COULEUR_BULLE_MOI if est_moi else COULEUR_BULLE_AUTRE
        bulle = tk.Frame(bloc, bg=couleur_bulle, padx=10, pady=6)
        bulle.grid(row=0, column=bulle_col, sticky="w")

        if not est_moi:
            tk.Label(
                bulle, text=pseudo, font=("Segoe UI", 8, "bold"),
                fg=couleur_pour_pseudo(pseudo), bg=couleur_bulle
            ).pack(anchor="w")

        tk.Label(
            bulle, text=texte, font=("Segoe UI", 10), bg=couleur_bulle,
            wraplength=220, justify="left", anchor="w"
        ).pack(anchor="w")
        tk.Label(
            bulle, text=heure, font=("Segoe UI", 7), fg="#999999", bg=couleur_bulle
        ).pack(anchor="e")

        self._scroll_vers_le_bas()

    def _scroll_vers_le_bas(self):
        self.master.update_idletasks()
        self.canvas.yview_moveto(1.0)

    # ------------------------------------------------------------------
    #  RÉSEAU
    # ------------------------------------------------------------------
    def send_message(self, event=None):
        msg = self.entry_msg.get().strip()
        if not msg or not self.client_socket:
            return
        try:
            self.client_socket.send((msg + "\n").encode('utf-8'))
            self.add_chat_message(self.username, msg, est_moi=True)
            self.entry_msg.delete(0, tk.END)
        except Exception:
            self.add_system_message("Échec de l'envoi du message.")

    def receive_messages(self):
        """Tourne dans un thread séparé : ne touche JAMAIS directement aux widgets Tkinter,
        on planifie chaque mise à jour via master.after() pour rester thread-safe.

        TCP ne préserve pas les frontières de message : on bufferise les octets reçus
        et on ne traite un message que lorsqu'on a rencontré son délimiteur '\\n'."""
        buffer = b""
        while True:
            try:
                data = self.client_socket.recv(1024)
                if not data:
                    break
                buffer += data
                while b"\n" in buffer:
                    ligne, buffer = buffer.split(b"\n", 1)
                    message = ligne.decode('utf-8', errors='replace')
                    self.master.after(0, self._traiter_message_recu, message)
            except Exception:
                break
        self.master.after(0, self.add_system_message, "Connexion au serveur interrompue.")

    def _traiter_message_recu(self, message):
        if message.startswith("SERVEUR:"):
            self.add_system_message(message[len("SERVEUR:"):].strip())
        elif ": " in message:
            pseudo, texte = message.split(": ", 1)
            self.add_chat_message(pseudo, texte, est_moi=False)
        else:
            self.add_chat_message("?", message, est_moi=False)

    def on_closing(self):
        try:
            if self.client_socket:
                self.client_socket.close()
        except Exception:
            pass
        self.master.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ChatClientGUI(root)
    root.mainloop()
