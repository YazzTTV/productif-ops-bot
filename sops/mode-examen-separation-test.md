# SOP - Test séparation Mode Examen / Focus

Source: `[C] Protocole Test - Separation Mode Examen et Focus (10 aout).md`.

Règle d'arrêt: T1 à T5 décident du commit. Si un test échoue, ne pas commiter les 7 fichiers.

1. T1: Assistant -> carte Mode Examen -> bouton du bas.
   - Attendu: écran "Démarrer le mode examen" avec durée, tâche principale, hard mode.
   - Échec: preview/paywall ou boucle setup-preview.
2. T2: sans application choisie, l'interrupteur "Bloquer les applications" reste inactif.
3. T3: choisir TikTok/Instagram, activer blocage, lancer session, ouvrir TikTok.
   - Attendu: bouclier + Dynamic Island "Bloc de révision".
4. T4: hard mode activé, glissement depuis le bord gauche.
   - Attendu: impossible de sortir.
5. T5: pendant une session examen, lancer puis terminer un Focus.
   - Attendu: TikTok reste bloqué, Focus ne propose pas "Arrêter le blocage".
6. Si T1-T5 passent: commiter les 7 fichiers.
7. Preuve attendue: résultat T1-T5 + commit si passé.

