# 💬 i-TAFA — Chat en utilisant Socket

**i-TAFA** est une application de messagerie instantanée en réseau local, développée en Python avec les sockets TCP et une interface graphique Tkinter inspirée de WhatsApp.

Le projet est composé de deux programmes :

- **`server.py`** — le serveur, qui relie tous les participants entre eux et affiche qui est connecté ;
- **`client.py`** — le client, l'application que chaque personne lance pour discuter.

---

## Sommaire

- [Aperçu](#aperçu)
- [Fonctionnalités](#fonctionnalités)
- [Architecture du projet](#architecture-du-projet)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Utilisation](#utilisation)
- [Fonctionnement en réseau (plusieurs ordinateurs)](#fonctionnement-en-réseau-plusieurs-ordinateurs)
- [Protocole de communication](#protocole-de-communication)
- [Dépannage](#dépannage)
- [Limites connues](#limites-connues)
- [Pistes d'amélioration](#pistes-damélioration)

---

## Aperçu

- Un ordinateur du réseau lance **`server.py`** : il joue le rôle de standard téléphonique, relie tous les clients entre eux et affiche en direct qui est connecté.
- Chaque participant (sur le même ordinateur ou sur un autre ordinateur du même réseau) lance **`client.py`**, choisit un pseudo, saisit l'adresse IP du serveur et rejoint la discussion.
- Tous les messages envoyés par un participant sont retransmis instantanément à tous les autres (chat de groupe).

## Fonctionnalités

**Côté client (`client.py`)**

- Écran de connexion avec pseudo, adresse IP du serveur et port
- Interface façon WhatsApp : bulles de message vertes (soi-même) / blanches (les autres)
- Avatar rond avec l'initiale du pseudo, coloré de façon stable (la même personne garde toujours la même couleur)
- Horodatage de chaque message
- Notifications d'arrivée et de départ des autres participants
- Réception réseau dans un thread séparé, sans jamais bloquer l'interface

**Côté serveur (`server.py`)**

- Interface graphique avec :
  - l'**adresse IP** et le **port** du serveur, chacun avec son propre bouton « Copier »
  - un bouton **Actualiser l'IP** (utile si l'ordinateur change de réseau)
  - la **liste des utilisateurs connectés** (pseudo, adresse, heure de connexion), mise à jour en direct
  - un **journal d'activité** horodaté (connexions, déconnexions, messages, erreurs)
  - un bouton pour **arrêter / redémarrer** le serveur sans fermer la fenêtre
- Gestion de plusieurs clients simultanés grâce aux threads, avec un verrou (`Lock`) pour éviter toute corruption de données en cas d'accès concurrent

## Architecture du projet

```
i-TAFA/
├── client.py     # Application cliente (interface + connexion réseau)
├── server.py     # Serveur (logique réseau + interface graphique)
└── README.md     # Ce document
```

`server.py` sépare volontairement deux responsabilités, selon le principe de séparation des préoccupations :

| Composant      | Rôle                                                                                                |
| -------------- | --------------------------------------------------------------------------------------------------- |
| `ServeurCoeur` | Logique réseau pure (sockets, threads, diffusion des messages). Ne dépend pas de Tkinter.           |
| `ServeurGUI`   | Interface graphique. Affiche l'état de `ServeurCoeur` et réagit à ses événements via des callbacks. |

Cette séparation permet, par exemple, de tester toute la logique réseau sans jamais ouvrir de fenêtre, et de faire évoluer l'interface sans toucher au fonctionnement du réseau.

## Prérequis

- **Python 3.8 ou supérieur**
- **Tkinter** (inclus par défaut avec Python sur Windows et macOS)
  - Sur certaines distributions Linux, il faut l'installer séparément :
    ```bash
    sudo apt install python3-tk
    ```
- Aucune bibliothèque externe n'est nécessaire : le projet n'utilise que la bibliothèque standard de Python (`socket`, `threading`, `hashlib`, `time`, `tkinter`).

## Installation

1. Récupérez les fichiers `client.py` et `server.py` (et ce `README.md`) dans un même dossier.
2. Vérifiez que Python 3 est installé :
   ```bash
   python3 --version
   ```
3. Aucune installation supplémentaire n'est requise (`pip install` n'est pas nécessaire).

## Utilisation

### 1. Démarrer le serveur

Sur **un seul ordinateur** du réseau (celui qui va héberger la discussion) :

```bash
python3 server.py
```

Une fenêtre s'ouvre et affiche l'**adresse IP** et le **port** (par défaut `5000`) à communiquer aux autres participants.

### 2. Se connecter avec un client

Sur **chaque ordinateur** qui souhaite participer à la discussion (y compris celui du serveur, si besoin) :

```bash
python3 client.py
```

Dans l'écran de connexion :

1. Saisissez un **pseudo**
2. Saisissez l'**adresse IP** affichée par le serveur (bouton « Copier l'IP » côté serveur)
3. Laissez le **port** par défaut (`5000`) sauf indication contraire du serveur
4. Cliquez sur **Se connecter**

Vous pouvez alors discuter : tous les messages sont visibles par toutes les personnes connectées.

## Fonctionnement en réseau (plusieurs ordinateurs)

Pour que deux ordinateurs différents puissent discuter ensemble :

- Les deux machines doivent être connectées **au même réseau local** (même Wi-Fi ou même réseau filaire).
- Le client doit utiliser l'**adresse IP locale réelle** du serveur (par exemple `192.168.1.23`), et non `127.0.0.1` (qui ne désigne que « cet ordinateur-ci »).
- Le **pare-feu** de l'ordinateur qui héberge le serveur doit autoriser les connexions entrantes sur le port utilisé (`5000` par défaut).
- Si le serveur affiche plusieurs adresses IP possibles (cas d'un ordinateur avec Wi-Fi _et_ câble Ethernet, par exemple), testez l'adresse principale affichée en premier.

## Protocole de communication

La communication repose sur des sockets TCP. Chaque message texte est terminé par un caractère de fin de ligne (`\n`), ce qui permet de découper correctement le flux réseau même si plusieurs messages sont envoyés très rapidement (TCP ne préserve pas naturellement les frontières entre messages).

| Étape                    | Contenu envoyé                         |
| ------------------------ | -------------------------------------- |
| Connexion d'un client    | Le client envoie son pseudo en premier |
| Message d'un utilisateur | `pseudo: message`                      |
| Notification système     | `SERVEUR: <texte de la notification>`  |

## Dépannage

| Problème                                                 | Cause probable / solution                                                                                             |
| -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| « Impossible de se connecter au serveur »                | Le serveur n'est pas démarré, l'adresse IP saisie est incorrecte, ou le pare-feu bloque le port.                      |
| Le client se connecte mais rien ne s'affiche             | Vérifiez que le port utilisé côté client correspond bien à celui affiché côté serveur.                                |
| `ModuleNotFoundError: No module named 'tkinter'` (Linux) | Installez le paquet : `sudo apt install python3-tk`.                                                                  |
| `OSError: [Errno 98] Address already in use`             | Le port est déjà utilisé par une autre instance du serveur ; attendez quelques secondes ou changez de port.           |
| Ça fonctionne en local mais pas entre deux ordinateurs   | Vérifiez que les deux machines sont sur le même réseau et que `127.0.0.1` n'a pas été utilisé par erreur côté client. |

## Limites connues

- Un seul salon de discussion global (pas de discussions privées ni de salons multiples)
- Les messages ne sont pas chiffrés : à réserver à un réseau local de confiance
- Aucun historique des messages n'est conservé après fermeture de l'application
- Aucune authentification : deux personnes peuvent choisir le même pseudo

## Pistes d'amélioration

- Messages privés entre deux utilisateurs
- Historique des conversations sauvegardé dans un fichier
- Envoi de fichiers ou d'images
- Chiffrement des échanges (TLS/SSL)
- Salons de discussion multiples
