# Règles Générales de Co-Développement (AGENT.md)

Ce document consigne les règles impératives régissant la collaboration entre l'utilisateur : TAHIRI MY AHMED et l'agent d'assistance pour le projet **Datacom Kudos**.

---

## 📜 RÈGLE 1 : Exécution des Commandes par l'Utilisateur
* **Principe :** L'agent **ne doit pas exécuter les commandes système / terminal à la place de l'utilisateur**.
* **Application :** L'agent fournit les commandes terminal de manière claire, explicite et prête à l'emploi (dans des blocs de code avec explications), mais **c'est l'utilisateur qui les tape et les exécute dans sa console**.

---

## 📜 RÈGLE 2 : Code Entièrement Commenté et Pédagogique
* **Principe :** Tout le code source produit doit être rigoureusement commenté pour garantir une compréhension immédiate du fonctionnement.
* **Application :**
  - Chaque fichier commence par un en-tête expliquant son rôle.
  - Chaque fonction, composant, structure de données et route d'API doit être documenté (paramètres, retour, logique interne).
  - Les commentaires doivent être rédigés en Anglais, clairs et accessibles.

---

## 📜 RÈGLE 3 : Respect Strict du Plan Étape par Étape
* **Principe :** Le développement avance de manière incrémentale, sans sauter d'étapes et sans surcharger l'utilisateur.
* **Application :** 
  - Suivre fidèlement l'ordre défini dans `SPECIFICATION.md` (de l'étape 1 à l'étape 7).
  - Terminer et valider une étape avant de passer à la suivante.
  - Résumer ce qui a été fait à chaque étape et expliquer ce que fait le code.

---

## 📜 RÈGLE 4 : Validation Préalable des Choix Techniques (Technologies / Librairies / Architecture)
* **Principe :** Aucune technologie, bibliothèque externe ou décision architecturale majeure ne doit être imposée sans accord préalable.
* **Application :**
  - Avant d'installer un package ou de choisir une structure de projet, l'agent doit :
    1. Nommer clairement la technologie / librairie proposée.
    2. Expliquer précisément **POURQUOI** ce choix est recommandé (avantages, simplicité, adéquation avec le sujet).
    3. Lister les alternatives possibles si pertinent.
    4. **Attendre explicitement la validation et le feu vert de l'utilisateur** avant de générer le code ou de faire exécuter une installation.

---

## 🎯 Objectif Pédagogique
Permettre à l'utilisateur de maîtriser à 100% son projet, de comprendre chaque ligne de code et d'être capable de le présenter et de le défendre avec assurance devant les évaluateurs de Datacom.
