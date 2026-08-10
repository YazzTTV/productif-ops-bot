# SOP - Checklist TestFlight 25 minutes

Source: `[C] Checklist Test Avant Soumission App Store - 1.0.9 (5).md`.

Conditions obligatoires:

- build TestFlight, pas build de développement ;
- compte non premium + sandbox App Store.

Tests minimum:

1. A1: essai gratuit réellement livré.
   - La feuille Apple doit annoncer 1 semaine gratuite puis prix et date de premier débit J+7.
2. A2: prix paywall = prix feuille Apple.
   - Même montant, en euros.
3. A4: parcours reviewer complet.
   - Connexion `apple-review@productif.io`, autorisation Temps d'écran, atteindre Mode Examen, lancer session.
4. B1: le blocage bloque vraiment TikTok/Instagram.
5. B2: retrait autorisation Temps d'écran.
   - L'app doit refuser d'activer le blocage et afficher l'état ambre.

Règle: arrêt à la première erreur bloquante.

