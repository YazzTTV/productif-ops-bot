# SOP - Corrections Superwall avant archive

Source: `[C] Chantier Superwall - Corrections Avant Soumission.md`.

Ordre obligatoire avant archive Xcode.

1. Trouver quelle campagne sert `FR Performance driven`.
2. Débrancher ou supprimer ce paywall fitness non modifié.
3. Réimporter les produits depuis App Store Connect.
4. Vérifier si les prix passent de dollars à euros.
5. Remplacer tous les montants tapés à la main par variables Superwall:
   - `{{ products.primary.price }}`
   - `{{ products.primary.localizedPeriod }}`
   - `{{ products.primary.trialPeriodDays }}`
   - `{{ products.primary.trialPeriodText }}`
6. Conditionner l'essai:
   - si `products.hasIntroductoryOffer`: afficher 7 jours gratuits.
   - sinon ne jamais promettre l'essai.
7. Passer la langue en français: Mensuel, Annuel, Annuler à tout moment, Restaurer les achats.
8. Paywall rentrée:
   - défaut sur annuel ;
   - produit `io.productif.app.premium.yearly.rentree` ;
   - 49 € visible ;
   - 59 € barré ;
   - 48,9 % d'économie ;
   - date fin 15 septembre.
9. Vérifier les trois IDs produits caractère par caractère:
   - `io.productif.app.premium.monthly`
   - `io.productif.app.premium.yearly`
   - `io.productif.app.premium.yearly.rentree`
10. Preuve attendue: captures des paywalls corrigés + absence de `$`, `Monthly`, `Yearly`, montants codés en dur.

