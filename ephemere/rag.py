"""Base de connaissances de Tessaline et recherche BM25 (exigences F1 et F2).

Pourquoi BM25 ecrit a la main plutot qu'une bibliotheque de vecteurs :
le sujet autorise les frameworks "si vous savez expliquer leur fonctionnement
interne". BM25 tient en soixante lignes, se demontre au tableau, et ne demande
aucun telechargement. Sur un corpus de dix documents, un moteur vectoriel
n'apporterait rien de mesurable et serait plus dur a defendre.

Deux filtres s'appliquent AVANT le classement, et ils ne sont pas cosmetiques :

  le temps   un article paru au jour 9 n'existe pas pour un agent qui decide
             au jour 4. Sans ce filtre, les agents citeraient l'avenir, et
             l'exigence C6 tomberait.
  le groupe  la charte de l'atelier de design n'est lisible que par ses
             membres. Un refractaire de la residence B n'y a pas acces.
"""
import math
import os
import re
import unicodedata

# Mots trop frequents pour discriminer quoi que ce soit.
VIDES = {
    "le", "la", "les", "un", "une", "des", "du", "de", "et", "ou", "a", "au",
    "aux", "ce", "cet", "cette", "ces", "qui", "que", "quoi", "dont", "pour",
    "par", "sur", "dans", "en", "est", "sont", "etait", "ete", "avec", "sans",
    "plus", "moins", "pas", "ne", "se", "sa", "son", "ses", "leur", "leurs",
    "il", "elle", "ils", "elles", "on", "nous", "vous", "je", "tu", "me", "te",
    "y", "mais", "donc", "car", "si", "tout", "tous", "toute", "toutes", "meme",
    "deja", "encore", "aussi", "comme", "entre", "apres", "avant", "chez",
    "leurs", "cela", "ca", "the", "of",
}


def normaliser(texte):
    t = unicodedata.normalize("NFD", texte.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return t


def decouper(texte):
    """Mots utiles d'un texte : minuscules, sans accents, sans mots vides."""
    return [m for m in re.findall(r"[a-z]+", normaliser(texte))
            if len(m) > 2 and m not in VIDES]


class Document:
    def __init__(self, entete, passage, numero):
        self.id = entete.get("id", "?")
        self.titre = entete.get("titre", "")
        self.source = entete.get("source", "")
        self.jour = int(entete.get("jour", 0))
        groupes = entete.get("groupes", "tous")
        self.groupes = ("tous" if groupes.strip() == "tous"
                        else {g.strip() for g in groupes.split(",")})
        self.passage = passage
        self.numero = numero
        self.mots = decouper(passage)

    @property
    def reference(self):
        return f"{self.titre} ({self.source})"

    def lisible_par(self, groupe):
        return self.groupes == "tous" or groupe in self.groupes

    def existe_au_jour(self, jour):
        return self.jour <= jour


def lire_fichier(chemin):
    """Un fichier du corpus donne plusieurs passages, un par paragraphe."""
    entete, corps = {}, []
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            if ligne.startswith("--- "):
                cle, _, valeur = ligne[4:].partition(":")
                entete[cle.strip()] = valeur.strip()
            else:
                corps.append(ligne)
    if "id" not in entete:
        return []
    paragraphes = [p.strip().replace("\n", " ")
                   for p in "".join(corps).split("\n\n") if p.strip()]
    return [Document(entete, p, i) for i, p in enumerate(paragraphes)]


class Base:
    """Index BM25 du corpus. Construit une fois au lancement du run."""

    K1 = 1.5    # saturation : au-dela, repeter un mot n'aide plus
    B = 0.75    # correction de longueur : un long passage n'est pas avantage

    def __init__(self, dossier):
        self.documents = []
        if os.path.isdir(dossier):
            for nom in sorted(os.listdir(dossier)):
                if nom.endswith(".md") and not nom.startswith("00_"):
                    self.documents.extend(lire_fichier(os.path.join(dossier, nom)))
        self.n = len(self.documents)
        self.longueur_moyenne = (sum(len(d.mots) for d in self.documents) / self.n
                                 if self.n else 0.0)
        self.frequence_doc = {}
        for d in self.documents:
            for mot in set(d.mots):
                self.frequence_doc[mot] = self.frequence_doc.get(mot, 0) + 1

    def _idf(self, mot):
        nq = self.frequence_doc.get(mot, 0)
        # Formule BM25 classique : un mot present partout vaut presque zero.
        return math.log(1 + (self.n - nq + 0.5) / (nq + 0.5))

    def _score(self, doc, mots_requete):
        if not doc.mots:
            return 0.0
        total = 0.0
        longueur = len(doc.mots)
        for mot in mots_requete:
            f = doc.mots.count(mot)
            if not f:
                continue
            numerateur = f * (self.K1 + 1)
            denominateur = f + self.K1 * (1 - self.B + self.B * longueur
                                          / (self.longueur_moyenne or 1))
            total += self._idf(mot) * numerateur / denominateur
        return total

    def chercher(self, requete, jour, groupe, k=3, score_minimum=0.5):
        """Les k passages les plus pertinents, accessibles a cet agent ce jour-la."""
        mots = decouper(requete)
        if not mots:
            return []
        candidats = [d for d in self.documents
                     if d.existe_au_jour(jour) and d.lisible_par(groupe)]
        notes = [(self._score(d, mots), d) for d in candidats]
        notes = [(s, d) for s, d in notes if s >= score_minimum]
        notes.sort(key=lambda sd: -sd[0])
        # Un seul passage par document : sinon deux paragraphes du meme article
        # occupent deux des trois places, et l'agent lit deux fois la meme source.
        retenus, vus = [], set()
        for s, d in notes:
            if d.id not in vus:
                vus.add(d.id)
                retenus.append((s, d))
        return [{"id": d.id, "titre": d.titre, "source": d.source, "jour": d.jour,
                 "passage": d.passage, "numero": d.numero, "score": round(s, 3)}
                for s, d in retenus[:k]]

    def resume(self):
        fichiers = len({d.id for d in self.documents})
        return {"documents": fichiers, "passages": self.n,
                "vocabulaire": len(self.frequence_doc),
                "longueur_moyenne": round(self.longueur_moyenne, 1)}
