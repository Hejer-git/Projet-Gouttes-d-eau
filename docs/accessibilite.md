# Accessibilité — règles pour l'interface complète (phase ultérieure)

Cadre : article 47 de la loi n° 2005-102, **RGAA 4.1.2** (WCAG 2.1 AA) ; le RGAA 5 (WCAG 2.2) est annoncé pour fin 2026.
Un établissement public doit publier une déclaration d'accessibilité, un schéma pluriannuel (3 ans max) et un plan
d'actions annuel, et afficher le niveau de conformité en page d'accueil.

## Règles de conception retenues
1. Langue de la page déclarée (`lang="fr"`), titre de page unique, hiérarchie de titres logique.
2. Information jamais portée par la couleur seule (le risque est écrit : « Risque élevé » + pictogramme + pourcentage).
3. Contrastes ≥ 4,5:1 (texte), ≥ 3:1 (composants graphiques et focus).
4. Tout est utilisable au clavier, focus visible, ordre de tabulation logique, pas de piège clavier.
5. Graphiques accompagnés d'un tableau de données équivalent et d'une description textuelle.
6. Champs de formulaire étiquetés, format de date indiqué, messages d'erreur explicites et associés au champ.
7. Texte redimensionnable à 200 % sans perte, mise en page adaptative (320 px), pas de défilement à deux dimensions.
8. Pas de mouvement automatique ; respect de `prefers-reduced-motion`.
9. Messages d'état annoncés aux lecteurs d'écran (`role="status"` / `aria-live="polite"`).
10. Documents et mentions : déclaration d'accessibilité, contact, voies de recours.

## Limites connues du prototype Streamlit
Streamlit génère un HTML dont l'attribut `lang` et la structure ne sont pas entièrement maîtrisables : le prototype
applique les règles 2, 5, 6 et 10 autant que possible mais **ne prétend pas à la conformité RGAA**. L'interface
complète (phase 5) sera développée avec un framework permettant de contrôler le HTML, puis auditée.

## Outils de contrôle
axe DevTools, Lighthouse, WAVE, tests au clavier, lecteurs d'écran (NVDA, VoiceOver), audit RGAA par échantillon.
