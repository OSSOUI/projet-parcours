"""Client LLM compatible API OpenAI : Groq, OpenRouter, Ollama, Colibri.

Aucune dependance externe, urllib suffit. Le client sait appeler DEUX tailles
de modele (exigence A5) et compte separement les appels de chacune, parce que
c'est ce comptage qui prouve le levier de sobriete de l'exigence E5.

Il chronometre chaque appel : la latence reelle sert aussi a convertir le temps
de reflexion en temps simule dans le mode asynchrone.
"""
import hashlib
import json
import os
import time
import urllib.error
import urllib.request

FOURNISSEURS = {
    "groq": {"url": "https://api.groq.com/openai/v1/chat/completions",
             "cle": "GROQ_API_KEY"},
    "openrouter": {"url": "https://openrouter.ai/api/v1/chat/completions",
                   "cle": "OPENROUTER_API_KEY"},
    "ollama": {"url": "http://localhost:11434/v1/chat/completions", "cle": None,
               "env_url": "OLLAMA_URL"},
    # GLM-5.2 (744 Md de parametres, ~40 Md actifs) sous Colibri, sur la machine
    # de la classe. Seul le grand modele y passe : l'image Docker de Colibri ne
    # sert que GLM, le petit reste donc sous Ollama. Colibri lit les experts sur
    # le disque, un appel peut durer plusieurs minutes : delai long.
    "colibri": {"url": "http://localhost:5000/v1/chat/completions", "cle": None,
                "env_url": "COLIBRI_URL", "par_taille": {"llm_petit": "ollama"},
                "delai_s": 1800},
}


def _url(conf):
    """URL du fournisseur, remplacable par une variable (Docker, autre machine)."""
    return os.environ.get(conf.get("env_url", ""), "") or conf["url"]


def charger_env(chemin=".env"):
    """Charge un fichier .env simple (CLE=valeur) dans l'environnement."""
    if not os.path.exists(chemin):
        return
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.strip()
            if ligne and not ligne.startswith("#") and "=" in ligne:
                k, v = ligne.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


class ClientLLM:
    def __init__(self, fournisseur, modeles, pause=1.0, temperature=0.9, attente_max=90,
                 graine=None):
        if fournisseur not in FOURNISSEURS:
            raise SystemExit(f"Fournisseur inconnu : {fournisseur}")
        conf = FOURNISSEURS[fournisseur]
        self.fournisseur = fournisseur
        self.modeles = modeles            # {"llm_grand": "...", "llm_petit": "..."}
        par_taille = conf.get("par_taille", {})
        self.urls = {t: _url(FOURNISSEURS[par_taille[t]]) if t in par_taille else _url(conf)
                     for t in modeles}
        self.delai_s = conf.get("delai_s", 90)
        self.cle = os.environ.get(conf["cle"], "") if conf["cle"] else ""
        if conf["cle"] and not self.cle:
            raise SystemExit(f"Variable {conf['cle']} absente. Copiez .env.example en .env.")
        self.pause = pause
        self.temperature = temperature
        self.attente_max = attente_max
        # Graine du run (decision du 28 octobre) : chaque appel recoit une graine
        # derivee de celle-ci et d'une cle (agent, moment simule, type d'appel),
        # et non d'un compteur, pour que l'ordre des appels n'y change rien
        # (mode asynchrone). Meme prompt, meme cle, meme modele : meme reponse
        # (verifie sur Ollama, 4 appels sur 4, les deux modeles alternes).
        self.graine = graine
        self.compte = {}                  # par taille : appels, tokens, latences
        self.nb_erreurs = 0
        self.attente_totale = 0.0
        self.derniere_mesure = {}
        self.dernier_brut = None          # texte renvoye par le modele, mot pour mot
        self._dernier_quota = None

    def _casier(self, taille):
        return self.compte.setdefault(taille, {
            "modele": self.modeles[taille], "appels": 0, "erreurs": 0,
            "tokens_entree": 0, "tokens_sortie": 0, "latences": []})

    def _poster(self, url, corps):
        entetes = {"Content-Type": "application/json",
                   # Cloudflare, devant Groq, refuse l'User-Agent par defaut d'urllib.
                   "User-Agent": "ephemere/1.0"}
        if self.cle:
            entetes["Authorization"] = f"Bearer {self.cle}"
        req = urllib.request.Request(url,
                                     data=json.dumps(corps).encode("utf-8"),
                                     headers=entetes)
        with urllib.request.urlopen(req, timeout=self.delai_s) as rep:
            return json.loads(rep.read().decode("utf-8"))

    def graine_appel(self, cle):
        """Graine d'un appel, stable pour une meme graine de run et une meme cle."""
        if self.graine is None or cle is None:
            return None
        return int(hashlib.sha256(f"{self.graine}:{cle}".encode()).hexdigest()[:8], 16)

    def json(self, systeme, consigne, taille="llm_petit", essais=3, schema=None, cle=None):
        """Appelle le modele de la taille demandee. Renvoie un dict, ou None.

        schema : un schema JSON que la reponse doit respecter (sortie
        structuree). Ollama contraint alors la generation elle-meme ; sans
        schema, on demande seulement "un objet JSON".
        """
        if taille not in self.modeles:
            raise SystemExit(f"Taille de modele inconnue : {taille}")
        casier = self._casier(taille)
        corps = {"model": self.modeles[taille],
                 "messages": [{"role": "system", "content": systeme},
                              {"role": "user", "content": consigne}],
                 "temperature": self.temperature,
                 "response_format": ({"type": "json_schema",
                                      "json_schema": {"name": "reponse", "strict": True,
                                                      "schema": schema}}
                                     if schema else {"type": "json_object"})}
        graine = self.graine_appel(cle)
        if graine is not None:
            corps["seed"] = graine
        attente = self.pause
        mesure = {"taille": taille, "modele": self.modeles[taille], "latence_s": None,
                  "attente_s": 0.0, "essais": 0, "tokens_entree": 0, "tokens_sortie": 0,
                  "graine": graine}
        self.derniere_mesure = mesure
        self.dernier_brut = None

        for essai in range(essais):
            if attente:
                time.sleep(attente)
                mesure["attente_s"] = round(mesure["attente_s"] + attente, 2)
                self.attente_totale += attente
            mesure["essais"] = essai + 1
            t0 = time.perf_counter()
            try:
                rep = self._poster(self.urls[taille], corps)
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    mesure["echec"] = "quota"
                    detail = _message_erreur(e)
                    if detail and detail != self._dernier_quota:
                        print(f"    [quota : {detail[:200]}]")
                        self._dernier_quota = detail
                    demande = delai_demande(e.headers)
                    if demande is not None and demande > self.attente_max:
                        print(f"    [quota epuise : {demande:.0f}s a attendre, "
                              f"au-dela de la limite de {self.attente_max:.0f}s]")
                        break
                    attente = (demande + 0.5) if demande else min(60, attente * 2 + 5)
                    continue
                mesure["echec"] = f"http_{e.code}"
                casier["erreurs"] += 1
                self.nb_erreurs += 1
                print(f"    [erreur HTTP {e.code}] {_message_erreur(e)[:200]}")
                return None
            except (urllib.error.URLError, TimeoutError) as e:
                mesure["echec"] = "reseau"
                attente = min(60, max(1.0, attente) * 2)
                print(f"    [erreur reseau : {e}]")
                continue

            mesure.pop("echec", None)
            latence = time.perf_counter() - t0
            mesure["latence_s"] = round(latence, 3)
            casier["latences"].append(latence)
            casier["appels"] += 1
            usage = rep.get("usage") or {}
            mesure["tokens_entree"] = usage.get("prompt_tokens", 0)
            mesure["tokens_sortie"] = usage.get("completion_tokens", 0)
            casier["tokens_entree"] += mesure["tokens_entree"]
            casier["tokens_sortie"] += mesure["tokens_sortie"]
            try:
                texte = rep["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                mesure["echec"] = "reponse_malformee"
                casier["erreurs"] += 1
                self.nb_erreurs += 1
                self.dernier_brut = json.dumps(rep, ensure_ascii=False)[:4000]
                return None
            self.dernier_brut = texte if isinstance(texte, str) else repr(texte)
            return extraire_json(texte)

        casier["erreurs"] += 1
        self.nb_erreurs += 1
        return None

    def bilan(self):
        """Chiffres a mettre tels quels dans le bilan de sobriete (E4, E5)."""
        total = {"appels": 0, "tokens_entree": 0, "tokens_sortie": 0, "temps_llm_s": 0.0}
        par_taille = {}
        for taille, c in self.compte.items():
            lat = c["latences"]
            par_taille[taille] = {
                "modele": c["modele"], "appels": c["appels"], "erreurs": c["erreurs"],
                "tokens_entree": c["tokens_entree"], "tokens_sortie": c["tokens_sortie"],
                "latence_moy_s": round(sum(lat) / len(lat), 3) if lat else None,
                "latence_max_s": round(max(lat), 3) if lat else None,
            }
            total["appels"] += c["appels"]
            total["tokens_entree"] += c["tokens_entree"]
            total["tokens_sortie"] += c["tokens_sortie"]
            total["temps_llm_s"] += sum(lat)
        total["temps_llm_s"] = round(total["temps_llm_s"], 1)
        total["temps_attente_s"] = round(self.attente_totale, 1)
        total["erreurs"] = self.nb_erreurs
        total["fournisseur"] = self.fournisseur
        total["par_taille"] = par_taille
        return total


def _message_erreur(e):
    try:
        return json.loads(e.read())["error"]["message"]
    except Exception:
        return ""


def delai_demande(entetes):
    """Secondes qu'un 429 demande d'attendre, ou None si ce n'est pas indique."""
    if not entetes:
        return None
    brut = entetes.get("retry-after")
    if brut:
        try:
            return float(brut)
        except ValueError:
            pass
    delais = [duree_s(entetes.get(k)) for k in
              ("x-ratelimit-reset-tokens", "x-ratelimit-reset-requests")]
    delais = [d for d in delais if d is not None]
    return max(delais) if delais else None


def duree_s(texte):
    """Convertit "1h2m3.5s" ou "250ms" en secondes. None si illisible."""
    if not texte:
        return None
    total, nombre, i = 0.0, "", 0
    while i < len(texte):
        c = texte[i]
        if c.isdigit() or c == ".":
            nombre += c
        elif texte.startswith("ms", i) and nombre:
            total += float(nombre) / 1000
            nombre, i = "", i + 1
        elif c in "hms" and nombre:
            total += float(nombre) * {"h": 3600, "m": 60, "s": 1}[c]
            nombre = ""
        else:
            return None
        i += 1
    return total if not nombre else None


def extraire_json(texte):
    """Recupere le premier objet JSON d'un texte, meme entoure de bavardage."""
    if not texte:
        return None
    try:
        return json.loads(texte)
    except (json.JSONDecodeError, TypeError):
        pass
    debut, fin = texte.find("{"), texte.rfind("}")
    if debut != -1 and fin > debut:
        try:
            return json.loads(texte[debut:fin + 1])
        except json.JSONDecodeError:
            return None
    return None
