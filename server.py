import socket
import threading
import time
import tkinter as tk
from tkinter import ttk

HOST = '0.0.0.0'   # Écoute sur TOUTES les interfaces réseau -> indispensable pour accepter
                    # des connexions venant d'autres ordinateurs du réseau (pas seulement 127.0.0.1)
PORT = 5000

# --- Palette (cohérente avec client.py) ---
COULEUR_ENTETE  = "#075E54"
COULEUR_FOND    = "#ECE5DD"
COULEUR_ACCENT  = "#25D366"
COULEUR_ROUGE   = "#E53935"


def obtenir_ip_locale():
    """Détecte l'adresse IP locale de la machine sur le réseau (jamais 127.0.0.1).

    Astuce standard : on "connecte" une socket UDP vers une IP publique. Aucune
    donnée n'est réellement envoyée (UDP est sans connexion) ; ça sert juste à
    demander au système d'exploitation quelle interface réseau serait utilisée,
    et donc quelle est l'adresse IP locale correspondante.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"
    finally:
        s.close()


def obtenir_autres_ip(ip_principale):
    """Liste les autres adresses IP locales de la machine (cas des PC multi-cartes réseau)."""
    try:
        adresses = set(socket.gethostbyname_ex(socket.gethostname())[2])
    except Exception:
        adresses = set()
    adresses.discard("127.0.0.1")
    adresses.discard(ip_principale)
    return sorted(adresses)


# ==========================================================================
#  LOGIQUE RÉSEAU PURE — aucune dépendance à Tkinter, donc testable seule
#  et réutilisable (ex: version console) sans toucher à l'affichage.
#  Communique avec l'interface uniquement via des callbacks (observateur).
# ==========================================================================
class ServeurCoeur:
    def __init__(self, host=HOST, port=PORT,
                 on_log=None, on_client_connecte=None, on_client_deconnecte=None):
        self.host = host
        self.port = port
        self.on_log = on_log or (lambda msg: None)
        self.on_client_connecte = on_client_connecte or (lambda pseudo, adresse: None)
        self.on_client_deconnecte = on_client_deconnecte or (lambda pseudo, adresse: None)

        # clients : {socket -> {"pseudo": str, "adresse": "ip:port"}}
        self.clients = {}
        self.clients_lock = threading.Lock()
        self.server_socket = None
        self.en_cours = False

    # --- Cycle de vie ---
    def demarrer(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        self.en_cours = True
        threading.Thread(target=self._boucle_acceptation, daemon=True).start()

    def arreter(self):
        self.en_cours = False
        with self.clients_lock:
            sockets = list(self.clients.keys())
            self.clients.clear()
        for sock in sockets:
            try:
                sock.close()
            except Exception:
                pass
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass

    def nombre_clients(self):
        with self.clients_lock:
            return len(self.clients)

    # --- Boucle d'acceptation des connexions entrantes ---
    def _boucle_acceptation(self):
        while self.en_cours:
            try:
                client_socket, adresse = self.server_socket.accept()
            except OSError:
                break  # La socket serveur a été fermée -> arrêt propre
            threading.Thread(target=self._gerer_client, args=(client_socket, adresse), daemon=True).start()

    # --- Découpage du flux TCP en messages complets (délimiteur '\n') ---
    @staticmethod
    def _lire_lignes(sock):
        buffer = b""
        while True:
            try:
                data = sock.recv(1024)
            except Exception:
                return
            if not data:
                return
            buffer += data
            while b"\n" in buffer:
                ligne, buffer = buffer.split(b"\n", 1)
                yield ligne.decode("utf-8", errors="replace")

    def _diffuser(self, message, expediteur=None):
        with self.clients_lock:
            destinataires = list(self.clients.keys())
        for sock in destinataires:
            if sock is expediteur:
                continue
            try:
                sock.send(message)
            except Exception:
                self._retirer_client(sock)

    def _retirer_client(self, sock):
        info = None
        with self.clients_lock:
            if sock in self.clients:
                info = self.clients.pop(sock)
        try:
            sock.close()
        except Exception:
            pass
        if info:
            pseudo, adresse = info["pseudo"], info["adresse"]
            self.on_log(f"{pseudo} a quitté le chat ({adresse}).")
            self.on_client_deconnecte(pseudo, adresse)
            self._diffuser(f"SERVEUR: {pseudo} a quitté le chat.\n".encode("utf-8"))

    def _gerer_client(self, sock, adresse):
        adresse_str = f"{adresse[0]}:{adresse[1]}"
        lignes = self._lire_lignes(sock)
        try:
            # Convention : la toute première ligne envoyée par le client est son pseudo
            pseudo_brut = next(lignes, "").strip()
            pseudo = pseudo_brut if pseudo_brut else f"Invite-{adresse[1]}"

            with self.clients_lock:
                self.clients[sock] = {"pseudo": pseudo, "adresse": adresse_str}

            self.on_log(f"{pseudo} connecté depuis {adresse_str}")
            self.on_client_connecte(pseudo, adresse_str)
            self._diffuser(f"SERVEUR: {pseudo} a rejoint le chat.\n".encode("utf-8"), expediteur=sock)

            for texte in lignes:
                self.on_log(f"{pseudo}: {texte}")
                self._diffuser(f"{pseudo}: {texte}\n".encode("utf-8"), expediteur=sock)

        except (ConnectionResetError, ConnectionAbortedError):
            pass
        except Exception as e:
            self.on_log(f"Erreur avec {adresse_str} : {e}")
        finally:
            self._retirer_client(sock)


# ==========================================================================
#  INTERFACE GRAPHIQUE — ne contient aucune logique réseau : elle affiche
#  l'état de ServeurCoeur et réagit à ses callbacks.
# ==========================================================================
class ServeurGUI:
    def __init__(self, root, port=PORT):
        self.root = root
        self.port = port
        self.coeur = None

        self.root.title("i-TAFA — Serveur")
        self.root.geometry("680x480")
        self.root.minsize(560, 420)
        self.root.configure(bg=COULEUR_FOND)

        self.ip_locale = obtenir_ip_locale()

        self._construire_entete()
        self._construire_panneau_info()
        self._construire_corps()
        self._construire_pied()

        self.root.protocol("WM_DELETE_WINDOW", self.fermer)
        self.demarrer_serveur()

    # ------------------------------------------------------------------
    def _construire_entete(self):
        entete = tk.Frame(self.root, bg=COULEUR_ENTETE, height=60)
        entete.pack(fill="x")
        entete.pack_propagate(False)

        tk.Label(entete, text="💬 i-TAFA — Serveur", font=("Segoe UI", 14, "bold"),
                 bg=COULEUR_ENTETE, fg="white").pack(side="left", padx=15, pady=10)

        self.label_statut = tk.Label(entete, text="● Hors ligne", font=("Segoe UI", 10, "bold"),
                                      bg=COULEUR_ENTETE, fg="#FF8A80")
        self.label_statut.pack(side="right", padx=15)

    def _construire_panneau_info(self):
        info = tk.Frame(self.root, bg="white", padx=15, pady=10)
        info.pack(fill="x", padx=12, pady=(12, 6))
        info.columnconfigure(1, weight=1)

        tk.Label(info, text="Adresse IP :", font=("Segoe UI", 10, "bold"),
                 bg="white").grid(row=0, column=0, sticky="w")
        self.label_ip = tk.Label(info, text=self.ip_locale,
                                  font=("Segoe UI", 13, "bold"), fg=COULEUR_ENTETE, bg="white")
        self.label_ip.grid(row=0, column=1, sticky="w", padx=(8, 0))
        tk.Button(info, text="Copier l'IP", font=("Segoe UI", 9), relief="flat", bg="#EEEEEE",
                  command=self.copier_ip).grid(row=0, column=2, padx=(10, 0))
        tk.Button(info, text="Actualiser l'IP", font=("Segoe UI", 9), relief="flat", bg="#EEEEEE",
                  command=self.actualiser_ip).grid(row=0, column=3, padx=(6, 0))

        tk.Label(info, text="Port :", font=("Segoe UI", 10, "bold"),
                 bg="white").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.label_port = tk.Label(info, text=str(self.port),
                                    font=("Segoe UI", 13, "bold"), fg=COULEUR_ENTETE, bg="white")
        self.label_port.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(6, 0))
        tk.Button(info, text="Copier le port", font=("Segoe UI", 9), relief="flat", bg="#EEEEEE",
                  command=self.copier_port).grid(row=1, column=2, padx=(10, 0), pady=(6, 0))

        tk.Label(
            info, text="Dans i-TAFA (client), collez l'IP dans « Adresse IP du serveur »\net le port dans « Port » — ce sont deux champs séparés.",
            font=("Segoe UI", 8), fg="#888888", bg="white", justify="left"
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))

        autres = obtenir_autres_ip(self.ip_locale)
        if autres:
            tk.Label(
                info, text=f"Autre(s) IP possible(s) de cette machine : {', '.join(autres)}",
                font=("Segoe UI", 8), fg="#888888", bg="white", justify="left"
            ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(2, 0))

    def _construire_corps(self):
        corps = tk.Frame(self.root, bg=COULEUR_FOND)
        corps.pack(fill="both", expand=True, padx=12, pady=6)
        corps.columnconfigure(0, weight=1)
        corps.columnconfigure(1, weight=1)
        corps.rowconfigure(0, weight=1)

        # --- Liste des clients connectés ---
        cadre_clients = tk.Frame(corps, bg="white")
        cadre_clients.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        tk.Label(cadre_clients, text="Utilisateurs connectés", font=("Segoe UI", 10, "bold"),
                 bg="white", anchor="w").pack(fill="x", padx=8, pady=(8, 4))

        colonnes = ("pseudo", "adresse", "heure")
        self.arbre_clients = ttk.Treeview(cadre_clients, columns=colonnes, show="headings")
        self.arbre_clients.heading("pseudo", text="Pseudo")
        self.arbre_clients.heading("adresse", text="Adresse")
        self.arbre_clients.heading("heure", text="Connecté à")
        self.arbre_clients.column("pseudo", width=100)
        self.arbre_clients.column("adresse", width=130)
        self.arbre_clients.column("heure", width=80, anchor="center")
        self.arbre_clients.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # --- Journal d'activité ---
        cadre_journal = tk.Frame(corps, bg="white")
        cadre_journal.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        tk.Label(cadre_journal, text="Journal d'activité", font=("Segoe UI", 10, "bold"),
                 bg="white", anchor="w").pack(fill="x", padx=8, pady=(8, 4))

        cadre_scroll = tk.Frame(cadre_journal, bg="white")
        cadre_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        scrollbar = ttk.Scrollbar(cadre_scroll)
        scrollbar.pack(side="right", fill="y")
        self.zone_journal = tk.Text(cadre_scroll, wrap="word", font=("Consolas", 9),
                                     yscrollcommand=scrollbar.set, state="disabled", bg="#FAFAFA")
        self.zone_journal.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.zone_journal.yview)

    def _construire_pied(self):
        bas = tk.Frame(self.root, bg=COULEUR_FOND)
        bas.pack(fill="x", padx=12, pady=(0, 12))

        self.label_compteur = tk.Label(bas, text="0 utilisateur connecté", font=("Segoe UI", 9),
                                        bg=COULEUR_FOND, fg="#555555")
        self.label_compteur.pack(side="left")

        self.btn_toggle = tk.Button(bas, text="Arrêter le serveur", font=("Segoe UI", 9, "bold"),
                                     bg=COULEUR_ROUGE, fg="white", relief="flat", padx=10, pady=4,
                                     command=self.basculer_serveur)
        self.btn_toggle.pack(side="right")

    # ------------------------------------------------------------------
    #  Actions
    # ------------------------------------------------------------------
    def demarrer_serveur(self):
        self.coeur = ServeurCoeur(
            port=self.port,
            # Chaque callback ne fait que planifier une mise à jour via after() :
            # on reste dans le thread principal Tkinter, donc thread-safe.
            on_log=lambda msg: self.root.after(0, self._ajouter_log, msg),
            on_client_connecte=lambda pseudo, adresse: self.root.after(0, self._ajouter_client, pseudo, adresse),
            on_client_deconnecte=lambda pseudo, adresse: self.root.after(0, self._retirer_client_affichage, pseudo, adresse),
        )
        try:
            self.coeur.demarrer()
            self.label_statut.config(text="● En ligne", fg="#B9F6CA")
            self._ajouter_log(f"Serveur démarré sur {self.ip_locale}:{self.port}")
        except OSError as e:
            self.label_statut.config(text="● Erreur", fg=COULEUR_ROUGE)
            self._ajouter_log(f"Impossible de démarrer le serveur (port {self.port} déjà utilisé ?) : {e}")

    def basculer_serveur(self):
        if self.coeur and self.coeur.en_cours:
            self.coeur.arreter()
            self.label_statut.config(text="● Hors ligne", fg="#FF8A80")
            self.btn_toggle.config(text="Redémarrer le serveur", bg=COULEUR_ACCENT)
            self._ajouter_log("Serveur arrêté manuellement.")
            for item in self.arbre_clients.get_children():
                self.arbre_clients.delete(item)
            self._maj_compteur()
        else:
            self.demarrer_serveur()
            self.btn_toggle.config(text="Arrêter le serveur", bg=COULEUR_ROUGE)

    def copier_ip(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.ip_locale)
        self._ajouter_log("Adresse IP copiée dans le presse-papiers.")

    def copier_port(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(str(self.port))
        self._ajouter_log("Port copié dans le presse-papiers.")

    def actualiser_ip(self):
        self.ip_locale = obtenir_ip_locale()
        self.label_ip.config(text=self.ip_locale)
        self._ajouter_log("Adresse IP actualisée.")

    # ------------------------------------------------------------------
    #  Mises à jour de l'affichage (toujours appelées depuis le thread Tk)
    # ------------------------------------------------------------------
    def _ajouter_log(self, message):
        heure = time.strftime("%H:%M:%S")
        self.zone_journal.config(state="normal")
        self.zone_journal.insert(tk.END, f"[{heure}] {message}\n")
        self.zone_journal.see(tk.END)
        self.zone_journal.config(state="disabled")

    def _ajouter_client(self, pseudo, adresse):
        # 'adresse' (ip:port) sert d'identifiant unique de ligne : contrairement au
        # pseudo, deux connexions ne peuvent jamais avoir la même adresse en même temps.
        heure = time.strftime("%H:%M:%S")
        if self.arbre_clients.exists(adresse):
            self.arbre_clients.delete(adresse)
        self.arbre_clients.insert("", tk.END, iid=adresse, values=(pseudo, adresse, heure))
        self._maj_compteur()

    def _retirer_client_affichage(self, pseudo, adresse):
        if self.arbre_clients.exists(adresse):
            self.arbre_clients.delete(adresse)
        self._maj_compteur()

    def _maj_compteur(self):
        n = len(self.arbre_clients.get_children())
        self.label_compteur.config(text=f"{n} utilisateur{'s' if n > 1 else ''} connecté{'s' if n > 1 else ''}")

    def fermer(self):
        if self.coeur:
            self.coeur.arreter()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ServeurGUI(root)
    root.mainloop()
