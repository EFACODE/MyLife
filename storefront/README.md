# Atelier — premium Shopify storefront

A Shopify **Online Store 2.0** theme for a modern home & decoration brand.
Scandinavian / Japandi: neutral palette, generous whitespace, editorial
typography, soft shadows, and motion that stays between 250–500ms.

Reference points: Audo Copenhagen, ferm LIVING, MENU, MUJI, H&M Home, Zara Home.

---

## Install

The theme is a complete, standalone Shopify theme directory. From this folder:

```bash
# Shopify CLI 3.x
shopify theme dev   --store your-store.myshopify.com   # live preview
shopify theme push  --store your-store.myshopify.com --unpublished
shopify theme check                                    # linting
```

Or zip this directory's **contents** (not the folder itself) and upload it under
*Online Store → Themes → Add theme → Upload zip file*.

### Menus to create

The theme reads these menu handles. Create them in *Navigation*:

| Handle              | Used by                                               |
| ------------------- | ----------------------------------------------------- |
| `main-menu`         | Header + mega menu. Nest two levels for a mega panel. |
| `footer`            | Footer link columns                                   |
| `search-suggestions`| Optional shortcuts shown in the empty search overlay  |

A top-level `main-menu` item with children renders as a **mega menu**. To add a
promoted image card to one, add a *Mega menu* block to the Header section and set
its "Menu item title" to match the top-level item exactly (e.g. `Living Room`).

### Product filters

Filters come from Shopify's **Search & Discovery** app. Install it and configure
filters there; the collection page renders whatever it exposes, including price
ranges. No theme changes needed.

### Ratings

Star ratings read the standard `reviews.rating` / `reviews.rating_count`
metafields, which Judge.me, Loox, Okendo, Yotpo and Shopify Product Reviews all
write to. With no reviews, the rating row renders nothing rather than an empty
five-star row.

---

## Structure

```
layout/
  theme.liquid              Global shell: tokens, SEO, overlays, script boot
  gift_card.liquid          Standalone gift-card layout

templates/
  index.json                Homepage (hero → … → newsletter)
  product.json              Product page with sticky buy section
  collection.json           Collection with filters + sort
  cart.json  search.json  page.json  page.contact.json
  list-collections.json  blog.json  article.json  404.json
  gift_card.liquid
  product.quick-view.liquid Fragment for the quick view modal (layout none)
  product.card.liquid       Fragment for wishlist rows (layout none)
  customers/*.liquid        Login, register, account, orders, addresses

sections/
  header-group.json         Announcement bar + header
  footer-group.json         Footer
  announcement-bar.liquid   Rotating, optionally dismissible
  header.liquid             Sticky, mega menu, mobile drawer, transparent hero mode
  hero.liquid               Full-screen, parallax, text reveal
  featured-categories.liquid
  featured-products.liquid  Best sellers
  promo-banner.liquid       Soft gradient banner
  collection-grid.liquid    Editorial masonry
  reviews.liquid  newsletter.liquid  rich-text.liquid  contact-form.liquid
  main-product.liquid       Gallery, variants, accordions, trust badges
  main-collection.liquid    Facets, sort, pagination
  main-cart.liquid  cart-drawer.liquid
  related-products.liquid   Lazy, via the recommendations route
  recently-viewed.liquid    localStorage + one search request
  recently-viewed-results.liquid   Fragment section
  predictive-search.liquid  Fragment section
  main-search.liquid  main-page.liquid  main-blog.liquid  main-article.liquid
  main-list-collections.liquid  main-404.liquid

snippets/
  image.liquid              Responsive srcset, intrinsic size, lazy by default
  product-card.liquid       Hover swap, quick add, quick view, wishlist, rating
  price.liquid  rating.liquid  icon.liquid  pagination.liquid  breadcrumbs.liquid
  cart-item.liquid  cart-summary.liquid  cart-upsell.liquid  shipping-bar.liquid
  search-overlay.liquid  wishlist-drawer.liquid  quick-view-modal.liquid
  zoom-lightbox.liquid  social-icons.liquid
  meta-tags.liquid  structured-data.liquid

assets/
  base.css                  Whole design system, one request
  theme.js                  All behaviour, one deferred request
```

---

## Design tokens

Every value is a CSS custom property emitted from theme settings in
`layout/theme.liquid`, so the palette, radii and motion can be retuned from the
editor without touching CSS.

| Token                                   | Default   |
| --------------------------------------- | --------- |
| `--color-bg`                            | `#FFFFFF` |
| `--color-surface`                       | `#F7F7F5` |
| `--color-surface-alt`                   | `#E8E6E1` |
| `--color-line`                          | `#C8C3BA` |
| `--color-text`                          | `#222222` |
| `--radius-sm` / `--radius` / `--radius-lg` | 10 / 12 / 14px |
| `--duration`                            | 400ms     |
| `--page-width`                          | 1560px    |

Shadows are soft and neutral only (`--shadow-xs` → `--shadow-lg`); there are no
hard borders on cards. Glassmorphism is confined to `--glass-bg` /
`--glass-blur` and used on the stuck header, badges, the search overlay, toasts
and card hover actions — never over content that has to stay legible.

**Typography.** The stack prefers `Inter`, `Neue Haas Grotesk Display` and
`Suisse Intl` when installed locally, then falls back to the Shopify-hosted font
chosen in *Typography*. That gets the intended look on most devices while
guaranteeing a hosted fallback everywhere else, with no third-party font request.

---

## Components

| Component | Where |
| --- | --- |
| Mega menu | `sections/header.liquid`, `MegaMenu` — hover-with-intent on desktop, click/keyboard elsewhere |
| Search overlay | `snippets/search-overlay.liquid` + `sections/predictive-search.liquid`, debounced predictive search |
| Cart drawer | `sections/cart-drawer.liquid`, re-rendered through the Section Rendering API |
| Wishlist | `WishlistToggle` / `WishlistDrawer`, localStorage, no account needed |
| Recently viewed | `RecentlyViewed`, localStorage handles resolved in one search request |
| Announcement bar | Rotating messages, optional session dismiss |
| Breadcrumbs | `snippets/breadcrumbs.liquid`, keeps the collection in the product trail |
| Product filters | `FacetFilters`, URL-driven, history-aware, no page reload |
| Variant selector | `VariantPicker`, disables unreachable combinations, swatches for colour options |
| Quick view | `QuickView` fetching `?view=quick-view` on demand |
| Free shipping bar | `ShippingBar`, server-rendered then kept live |
| Discount code | `CartDiscount` via the `/discount/CODE` route |
| Upsell | `snippets/cart-upsell.liquid` |
| Image zoom | Pointer-tracked magnify on desktop, lightbox on touch |

### Cart mutations

`window.Atelier.cart` wraps `/cart/add.js`, `/cart/change.js` and
`/cart/update.js`. Every call asks Shopify to re-render any element carrying
`data-cart-section="<section id>"`, so the drawer, the cart page and the shipping
bar all stay consistent from one request. A `cart:updated` event carries the new
cart for anything else that needs it.

To have your own markup refresh with the cart, give it
`data-cart-section="{{ section.id }}"` and it joins the same round trip.

---

## Animations

All motion is CSS-driven where possible and capped at 250–500ms.

| Effect | Implementation |
| --- | --- |
| Fade in on scroll | `data-reveal` + one shared `IntersectionObserver` |
| Parallax hero | `data-parallax="0.14"`, one `requestAnimationFrame` loop for all layers |
| Text reveal | `data-text-reveal` splits into words that rise from a clipped baseline |
| Blur to sharp | Images decode from `blur(14px)` to sharp |
| Floating images | `.float`, a 9s eased drift |
| Hover scale / card lift | Transform + soft shadow on `.product-card` |
| Button ripple | One neutral pulse, delegated pointer listener |
| Sticky header | Condenses to glass, hides on scroll-down |
| Page transition | Veil fades in before same-origin navigation |
| Cursor effect | Trailing ring that grows over interactive elements |
| Smooth anchors | Offset for the sticky header, then focus moves for a11y |

Three guards keep this safe:

1. **`prefers-reduced-motion`** disables every animation, parallax transform and
   the custom cursor.
2. **The `.js` class**, set by an inline script in `<head>`, is required before
   any reveal starts hidden — a blocked or failed `theme.js` can never leave the
   page blank.
3. **Animations can be turned off entirely** in *Theme settings → Motion*.

---

## Performance

- Two asset requests total: one stylesheet, one deferred script. No framework,
  no jQuery, no icon font, no CDN dependency.
- `snippets/image.liquid` emits a real `srcset`, a `sizes` value matched to the
  layout, and intrinsic `width`/`height` so nothing shifts while loading.
- Everything is `loading="lazy"` except the hero and the first product image,
  which are `eager` with `fetchpriority="high"` as LCP candidates.
- The hero takes a separate mobile crop, so phones never download a 2400px
  landscape.
- Related products and recommendations load only when scrolled near
  (`IntersectionObserver`, 600px margin). Quick view fetches nothing until asked.
- Predictive search is debounced at 260ms and aborts in-flight requests.
- Icons are inline SVG, so there is no sprite request and no icon-font FOIT.

## SEO

- `snippets/meta-tags.liquid`: canonical, Open Graph, Twitter card, product
  price/availability metadata, and `rel=prev`/`next` on paginated listings.
- `snippets/structured-data.liquid`: JSON-LD for Organization, WebSite with
  SearchAction, Product with per-variant offers and aggregate rating,
  BreadcrumbList, CollectionPage/ItemList and Article.
- One `<h1>` per template, real heading order, and breadcrumbs on every page
  except the homepage and cart.

## Accessibility

Focus is trapped in drawers and modals and returned to the trigger on close.
Every overlay is a labelled `role="dialog"` with `aria-modal`. Icon-only
controls carry `aria-label`; toggles use `aria-pressed`; the cart count and
filter results announce through live regions. Focus rings are never removed —
`:focus-visible` is styled, not suppressed.

---

## Browser support

Evergreen Chrome, Edge, Firefox and Safari 15.4+. The theme leans on custom
elements, CSS custom properties, `:focus-visible`, `svh` units and
`backdrop-filter`; where `backdrop-filter` is unsupported, glass surfaces
degrade to a solid translucent background.
