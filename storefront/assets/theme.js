/* ==========================================================================
   Atelier — theme behaviour
   Vanilla, dependency-free, custom-element based. Every component is
   self-registering so sections can be added or reordered in the editor
   without touching this file.
   ========================================================================== */

(function () {
  'use strict';

  const theme = window.theme || {};
  const settings = theme.settings || {};
  const strings = theme.strings || {};
  const routes = theme.routes || {};

  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const motionOK = () => Boolean(settings.animations) && !prefersReducedMotion.matches;

  /* ------------------------------------------------------------------------
     Utilities
     ------------------------------------------------------------------------ */

  const debounce = (fn, wait = 200) => {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(null, args), wait);
    };
  };

  const formatMoney = (cents) => {
    const format = settings.moneyFormat || '${{amount}}';
    const value = Number(cents || 0) / 100;

    const withDelimiters = (precision, thousands = ',', decimal = '.') => {
      const fixed = value.toFixed(precision);
      const [int, dec] = fixed.split('.');
      const grouped = int.replace(/(\d)(?=(\d\d\d)+(?!\d))/g, `$1${thousands}`);
      return dec ? `${grouped}${decimal}${dec}` : grouped;
    };

    return format.replace(/\{\{\s*(\w+)\s*\}\}/, (_match, token) => {
      switch (token) {
        case 'amount':
          return withDelimiters(2);
        case 'amount_no_decimals':
          return withDelimiters(0);
        case 'amount_with_comma_separator':
          return withDelimiters(2, '.', ',');
        case 'amount_no_decimals_with_comma_separator':
          return withDelimiters(0, '.', ',');
        case 'amount_with_apostrophe_separator':
          return withDelimiters(2, "'");
        default:
          return withDelimiters(2);
      }
    });
  };

  const fetchConfig = (type = 'json') => ({
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: `application/${type}` }
  });

  const trapFocusables = (container) =>
    Array.from(
      container.querySelectorAll(
        'a[href], button:not([disabled]), input:not([type="hidden"]):not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])'
      )
    ).filter((el) => el.offsetParent !== null);

  let scrollLockCount = 0;
  let savedScrollY = 0;

  const lockScroll = () => {
    if (scrollLockCount === 0) {
      savedScrollY = window.scrollY;
      const scrollbar = window.innerWidth - document.documentElement.clientWidth;
      document.body.style.paddingRight = scrollbar > 0 ? `${scrollbar}px` : '';
      document.body.classList.add('overflow-hidden');
    }
    scrollLockCount += 1;
  };

  const unlockScroll = () => {
    scrollLockCount = Math.max(0, scrollLockCount - 1);
    if (scrollLockCount === 0) {
      document.body.classList.remove('overflow-hidden');
      document.body.style.paddingRight = '';
    }
  };

  const publish = (name, detail) => document.dispatchEvent(new CustomEvent(name, { detail }));

  /* ------------------------------------------------------------------------
     Toasts
     ------------------------------------------------------------------------ */

  const toast = (message, imageUrl) => {
    const stack = document.querySelector('[data-toast-stack]');
    if (!stack) return;

    const el = document.createElement('div');
    el.className = 'toast';
    el.setAttribute('role', 'status');

    if (imageUrl) {
      const img = document.createElement('img');
      img.className = 'toast__thumb';
      img.src = imageUrl;
      img.alt = '';
      img.loading = 'lazy';
      el.appendChild(img);
    }

    const text = document.createElement('span');
    text.textContent = message;
    el.appendChild(text);
    stack.appendChild(el);

    requestAnimationFrame(() => el.classList.add('is-visible'));

    setTimeout(() => {
      el.classList.remove('is-visible');
      el.addEventListener('transitionend', () => el.remove(), { once: true });
      setTimeout(() => el.remove(), 800);
    }, 3200);
  };

  /* ------------------------------------------------------------------------
     Scroll reveal — fade in / blur to sharp / text reveal
     ------------------------------------------------------------------------ */

  const revealObserver = motionOK()
    ? new IntersectionObserver(
        (entries, observer) => {
          entries.forEach((entry) => {
            if (!entry.isIntersecting) return;
            entry.target.classList.add('is-revealed');
            observer.unobserve(entry.target);
          });
        },
        { rootMargin: '0px 0px -8% 0px', threshold: 0.08 }
      )
    : null;

  const observeReveals = (root = document) => {
    const targets = root.querySelectorAll('[data-reveal]:not(.is-revealed)');
    if (!revealObserver) {
      targets.forEach((el) => el.classList.add('is-revealed'));
      return;
    }
    targets.forEach((el) => revealObserver.observe(el));
  };

  // Split headings into words so they can rise from a clipped baseline.
  const buildTextReveals = (root = document) => {
    root.querySelectorAll('[data-text-reveal]:not([data-text-reveal-ready])').forEach((el) => {
      el.setAttribute('data-text-reveal-ready', '');
      if (!motionOK()) return;

      const words = el.textContent.trim().split(/\s+/);
      el.textContent = '';
      el.classList.add('text-reveal');

      const line = document.createElement('span');
      line.className = 'text-reveal__line';

      words.forEach((word, index) => {
        const span = document.createElement('span');
        span.className = 'text-reveal__word';
        span.style.setProperty('--word-index', index);
        span.textContent = word;
        line.appendChild(span);
        if (index < words.length - 1) line.appendChild(document.createTextNode(' '));
      });

      el.appendChild(line);
    });
  };

  /* ------------------------------------------------------------------------
     Blur-to-sharp image loading
     ------------------------------------------------------------------------ */

  const initImageLoading = (root = document) => {
    root.querySelectorAll('.media img:not([data-load-bound])').forEach((img) => {
      img.setAttribute('data-load-bound', '');
      if (img.complete && img.naturalWidth > 0) {
        img.classList.remove('is-loading');
        return;
      }
      img.classList.add('is-loading');
      img.addEventListener('load', () => img.classList.remove('is-loading'), { once: true });
      img.addEventListener('error', () => img.classList.remove('is-loading'), { once: true });
    });
  };

  /* ------------------------------------------------------------------------
     Parallax — single rAF loop for every registered layer
     ------------------------------------------------------------------------ */

  const parallax = (() => {
    let layers = [];
    let ticking = false;

    const update = () => {
      const viewportHeight = window.innerHeight;

      layers.forEach((layer) => {
        const rect = layer.el.getBoundingClientRect();
        if (rect.bottom < -200 || rect.top > viewportHeight + 200) return;

        // Progress from -1 (entering below) to 1 (leaving above).
        const progress = (rect.top + rect.height / 2 - viewportHeight / 2) / viewportHeight;
        const offset = -progress * layer.speed * 100;
        layer.el.style.transform = `translate3d(0, ${offset.toFixed(2)}px, 0)`;
      });

      ticking = false;
    };

    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(update);
    };

    return {
      register(root = document) {
        if (!motionOK() || !settings.parallax) return;

        root.querySelectorAll('[data-parallax]').forEach((el) => {
          if (layers.some((layer) => layer.el === el)) return;
          const speed = parseFloat(el.dataset.parallax) || 0.18;
          layers.push({ el, speed });
        });

        if (layers.length && !this.bound) {
          this.bound = true;
          window.addEventListener('scroll', onScroll, { passive: true });
          window.addEventListener('resize', debounce(update, 150));
        }
        update();
      },
      refresh() {
        layers = layers.filter((layer) => layer.el.isConnected);
        update();
      }
    };
  })();

  /* ------------------------------------------------------------------------
     Button ripple
     ------------------------------------------------------------------------ */

  document.addEventListener('pointerdown', (event) => {
    if (!motionOK()) return;
    const button = event.target.closest('.button:not([disabled])');
    if (!button) return;

    const rect = button.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height);
    const ripple = document.createElement('span');
    ripple.className = 'ripple';
    ripple.style.width = ripple.style.height = `${size}px`;
    ripple.style.left = `${event.clientX - rect.left - size / 2}px`;
    ripple.style.top = `${event.clientY - rect.top - size / 2}px`;

    button.appendChild(ripple);
    setTimeout(() => ripple.remove(), 600);
  });

  /* ------------------------------------------------------------------------
     Cursor follower
     ------------------------------------------------------------------------ */

  const initCursor = () => {
    const cursor = document.querySelector('[data-cursor]');
    if (!cursor || !settings.cursor || !motionOK()) return;
    if (!window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;

    let targetX = window.innerWidth / 2;
    let targetY = window.innerHeight / 2;
    let x = targetX;
    let y = targetY;
    let running = false;

    const render = () => {
      // Eased trailing motion — the ring lags the pointer very slightly.
      x += (targetX - x) * 0.18;
      y += (targetY - y) * 0.18;
      cursor.style.transform = `translate3d(${x}px, ${y}px, 0)`;
      if (running) requestAnimationFrame(render);
    };

    window.addEventListener(
      'pointermove',
      (event) => {
        targetX = event.clientX;
        targetY = event.clientY;

        if (!running) {
          running = true;
          cursor.classList.add('is-visible');
          requestAnimationFrame(render);
        }

        const interactive = event.target.closest(
          'a, button, summary, .product-card, .category-card, .collection-tile, input, select, textarea, label'
        );
        cursor.classList.toggle('is-hovering', Boolean(interactive));
      },
      { passive: true }
    );

    document.addEventListener('pointerleave', () => cursor.classList.remove('is-visible'));
  };

  /* ------------------------------------------------------------------------
     Page transitions — veil out on same-origin navigations
     ------------------------------------------------------------------------ */

  const initPageTransition = () => {
    const veil = document.querySelector('[data-page-veil]');
    if (!veil || !settings.pageTransition || !motionOK()) return;

    document.addEventListener('click', (event) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;

      const link = event.target.closest('a[href]');
      if (!link) return;
      if (link.target === '_blank' || link.hasAttribute('download') || link.dataset.noTransition !== undefined) return;

      const url = new URL(link.href, window.location.href);
      if (url.origin !== window.location.origin) return;
      if (url.pathname === window.location.pathname && url.search === window.location.search) return;
      if (url.href.startsWith(`${window.location.href.split('#')[0]}#`)) return;

      event.preventDefault();
      veil.classList.add('is-active');
      setTimeout(() => {
        window.location.href = url.href;
      }, 240);
    });

    // Clear the veil if the browser restores the page from cache.
    window.addEventListener('pageshow', (event) => {
      if (event.persisted) veil.classList.remove('is-active');
    });
  };

  /* ------------------------------------------------------------------------
     Smooth anchor scroll
     ------------------------------------------------------------------------ */

  document.addEventListener('click', (event) => {
    const link = event.target.closest('a[href^="#"]:not([href="#"])');
    if (!link) return;

    const target = document.querySelector(link.getAttribute('href'));
    if (!target) return;

    event.preventDefault();
    const header = document.querySelector('.header');
    const offset = (header ? header.offsetHeight : 0) + 20;
    const top = target.getBoundingClientRect().top + window.scrollY - offset;

    window.scrollTo({ top, behavior: motionOK() ? 'smooth' : 'auto' });
    target.setAttribute('tabindex', '-1');
    target.focus({ preventScroll: true });
  });

  /* ------------------------------------------------------------------------
     Base overlay behaviour (drawers, overlays, modals)
     ------------------------------------------------------------------------ */

  class OverlayElement extends HTMLElement {
    constructor() {
      super();
      this.openClass = 'is-open';
      this.onKeydown = this.onKeydown.bind(this);
    }

    connectedCallback() {
      this.panel = this.querySelector('[data-overlay-panel]') || this;
      this.backdrop = this.querySelector('[data-overlay-backdrop]');

      this.addEventListener('click', (event) => {
        if (event.target.closest('[data-overlay-close]')) {
          event.preventDefault();
          this.close();
        } else if (this.backdrop && event.target === this.backdrop) {
          this.close();
        } else if (event.target === this && this.panel !== this) {
          this.close();
        }
      });
    }

    get isOpen() {
      return this.panel.classList.contains(this.openClass);
    }

    open(trigger) {
      if (this.isOpen) return;
      this.trigger = trigger || document.activeElement;

      if (this.backdrop) this.backdrop.classList.add('is-active');
      // The class lands on both host and panel so CSS can hook either one.
      this.panel.classList.add(this.openClass);
      this.classList.add(this.openClass);
      this.setAttribute('aria-hidden', 'false');
      lockScroll();
      document.addEventListener('keydown', this.onKeydown);

      requestAnimationFrame(() => {
        const focusTarget =
          this.querySelector('[data-overlay-autofocus]') || trapFocusables(this.panel)[0] || this.panel;
        focusTarget.focus({ preventScroll: true });
      });

      publish('overlay:open', { overlay: this });
    }

    close() {
      if (!this.isOpen) return;

      if (this.backdrop) this.backdrop.classList.remove('is-active');
      this.panel.classList.remove(this.openClass);
      this.classList.remove(this.openClass);
      this.setAttribute('aria-hidden', 'true');
      unlockScroll();
      document.removeEventListener('keydown', this.onKeydown);

      if (this.trigger && this.trigger.isConnected) this.trigger.focus({ preventScroll: true });
      publish('overlay:close', { overlay: this });
    }

    toggle(trigger) {
      this.isOpen ? this.close() : this.open(trigger);
    }

    onKeydown(event) {
      if (event.key === 'Escape') {
        event.stopPropagation();
        this.close();
        return;
      }

      if (event.key !== 'Tab') return;

      const focusables = trapFocusables(this.panel);
      if (!focusables.length) return;

      const first = focusables[0];
      const last = focusables[focusables.length - 1];

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  }

  customElements.define('overlay-element', OverlayElement);

  // Any element can open an overlay by id.
  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-overlay-open]');
    if (!trigger) return;

    const overlay = document.getElementById(trigger.dataset.overlayOpen);
    if (!overlay || typeof overlay.open !== 'function') return;

    event.preventDefault();
    overlay.open(trigger);
  });

  /* ------------------------------------------------------------------------
     Sticky header
     ------------------------------------------------------------------------ */

  class StickyHeader extends HTMLElement {
    connectedCallback() {
      this.header = this.querySelector('.header') || this;
      this.lastY = window.scrollY;
      this.hideOnScroll = this.dataset.hideOnScroll === 'true';
      this.onScroll = this.onScroll.bind(this);

      window.addEventListener('scroll', this.onScroll, { passive: true });
      this.onScroll();

      // Keep --header-height honest so sticky offsets stay aligned.
      if ('ResizeObserver' in window) {
        this.resizeObserver = new ResizeObserver(() => {
          document.documentElement.style.setProperty('--header-height', `${this.header.offsetHeight}px`);
        });
        this.resizeObserver.observe(this.header);
      }
    }

    disconnectedCallback() {
      window.removeEventListener('scroll', this.onScroll);
      if (this.resizeObserver) this.resizeObserver.disconnect();
    }

    onScroll() {
      const y = window.scrollY;
      this.header.classList.toggle('is-stuck', y > 24);

      if (this.hideOnScroll && !document.body.classList.contains('overflow-hidden')) {
        const scrollingDown = y > this.lastY && y > 260;
        const openMenu = this.querySelector('.header__menu-item.is-open');
        this.header.classList.toggle('is-hidden', scrollingDown && !openMenu);
      }

      this.lastY = y;
    }
  }

  customElements.define('sticky-header', StickyHeader);

  /* ------------------------------------------------------------------------
     Mega menu — hover with intent on desktop, click/keyboard everywhere
     ------------------------------------------------------------------------ */

  class MegaMenu extends HTMLElement {
    connectedCallback() {
      this.items = Array.from(this.querySelectorAll('.header__menu-item--has-menu'));
      this.canHover = window.matchMedia('(hover: hover) and (min-width: 990px)').matches;

      this.items.forEach((item) => {
        const link = item.querySelector('.header__menu-link');
        const panel = item.querySelector('.mega-menu');
        if (!link || !panel) return;

        link.setAttribute('aria-expanded', 'false');
        link.setAttribute('aria-haspopup', 'true');

        if (this.canHover) {
          let enterTimer;
          let leaveTimer;

          item.addEventListener('pointerenter', () => {
            clearTimeout(leaveTimer);
            enterTimer = setTimeout(() => this.openItem(item), 90);
          });

          item.addEventListener('pointerleave', () => {
            clearTimeout(enterTimer);
            leaveTimer = setTimeout(() => this.closeItem(item), 160);
          });
        }

        // Keyboard and touch: the link toggles rather than navigates on first press.
        link.addEventListener('click', (event) => {
          if (this.canHover) return;
          if (!item.classList.contains('is-open')) {
            event.preventDefault();
            this.closeAll();
            this.openItem(item);
          }
        });

        item.addEventListener('focusin', () => this.openItem(item));
        item.addEventListener('focusout', (event) => {
          if (!item.contains(event.relatedTarget)) this.closeItem(item);
        });
      });

      document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') this.closeAll();
      });

      document.addEventListener('pointerdown', (event) => {
        if (!this.contains(event.target)) this.closeAll();
      });
    }

    openItem(item) {
      this.closeAll(item);
      item.classList.add('is-open');
      const link = item.querySelector('.header__menu-link');
      if (link) link.setAttribute('aria-expanded', 'true');
    }

    closeItem(item) {
      item.classList.remove('is-open');
      const link = item.querySelector('.header__menu-link');
      if (link) link.setAttribute('aria-expanded', 'false');
    }

    closeAll(except) {
      this.items.forEach((item) => {
        if (item !== except) this.closeItem(item);
      });
    }
  }

  customElements.define('mega-menu', MegaMenu);

  /* ------------------------------------------------------------------------
     Predictive search overlay
     ------------------------------------------------------------------------ */

  class SearchOverlay extends OverlayElement {
    connectedCallback() {
      super.connectedCallback();

      this.input = this.querySelector('[data-search-input]');
      this.results = this.querySelector('[data-search-results]');
      this.defaultContent = this.querySelector('[data-search-default]');
      this.abortController = null;

      if (!this.input) return;

      this.input.addEventListener(
        'input',
        debounce(() => this.search(this.input.value.trim()), 260)
      );

      this.querySelector('form').addEventListener('submit', (event) => {
        if (!this.input.value.trim()) event.preventDefault();
      });
    }

    async search(term) {
      if (this.abortController) this.abortController.abort();

      if (term.length < 2) {
        this.results.innerHTML = '';
        if (this.defaultContent) this.defaultContent.hidden = false;
        return;
      }

      if (this.defaultContent) this.defaultContent.hidden = true;
      this.abortController = new AbortController();

      const params = new URLSearchParams({
        q: term,
        'resources[type]': 'product,collection,page,article',
        'resources[limit]': '6',
        'resources[options][unavailable_products]': 'last',
        section_id: 'predictive-search'
      });

      try {
        const response = await fetch(`${routes.predictiveSearch}?${params}`, {
          signal: this.abortController.signal
        });
        if (!response.ok) throw new Error('Search failed');

        const markup = await response.text();
        const doc = new DOMParser().parseFromString(markup, 'text/html');
        const fragment = doc.querySelector('[data-predictive-results]');
        this.results.innerHTML = fragment ? fragment.innerHTML : '';
        initImageLoading(this.results);
      } catch (error) {
        if (error.name !== 'AbortError') this.results.innerHTML = '';
      }
    }

    open(trigger) {
      super.open(trigger);
      if (this.input) requestAnimationFrame(() => this.input.focus());
    }
  }

  customElements.define('search-overlay', SearchOverlay);

  /* ------------------------------------------------------------------------
     Cart
     ------------------------------------------------------------------------ */

  const cart = {
    /** Sections that should re-render after every cart mutation. */
    sectionsToRender() {
      return Array.from(document.querySelectorAll('[data-cart-section]'))
        .map((el) => el.dataset.cartSection)
        .filter(Boolean);
    },

    async request(url, body) {
      const sections = this.sectionsToRender();
      const payload = Object.assign({}, body, {
        sections: sections.join(','),
        sections_url: window.location.pathname
      });

      const response = await fetch(url, Object.assign(fetchConfig(), { body: JSON.stringify(payload) }));
      const data = await response.json();

      if (!response.ok || data.status) {
        throw Object.assign(new Error(data.description || data.message || 'Cart error'), { data });
      }

      this.renderSections(data);
      publish('cart:updated', { cart: data });
      return data;
    },

    renderSections(data) {
      if (!data.sections) return;

      Object.entries(data.sections).forEach(([id, markup]) => {
        const target = document.querySelector(`[data-cart-section="${id}"]`);
        if (!target || !markup) return;

        const doc = new DOMParser().parseFromString(markup, 'text/html');
        const source = doc.querySelector(`[data-cart-section="${id}"]`) || doc.querySelector('.shopify-section');
        if (source) {
          target.innerHTML = source.innerHTML;
          initImageLoading(target);
          observeReveals(target);
        }
      });
    },

    async add(items) {
      return this.request(routes.cartAdd, { items: Array.isArray(items) ? items : [items] });
    },

    async change(payload) {
      return this.request(routes.cartChange, payload);
    },

    async update(payload) {
      return this.request(routes.cartUpdate, payload);
    },

    async fetchState() {
      const response = await fetch(`${routes.cart}.js`, { headers: { Accept: 'application/json' } });
      return response.json();
    },

    openDrawer() {
      const drawer = document.getElementById('CartDrawer');
      if (settings.cartDrawer && drawer && typeof drawer.open === 'function') {
        drawer.open();
        return true;
      }
      return false;
    }
  };

  /* Add to cart — works for product forms, quick add and upsells. */
  class ProductForm extends HTMLElement {
    connectedCallback() {
      this.form = this.querySelector('form');
      if (!this.form) return;

      this.submitButton = this.querySelector('[type="submit"]');
      this.errorTarget = this.querySelector('[data-form-error]');
      this.form.addEventListener('submit', (event) => this.onSubmit(event));
    }

    async onSubmit(event) {
      event.preventDefault();
      if (this.submitButton && this.submitButton.getAttribute('aria-disabled') === 'true') return;

      this.setLoading(true);
      if (this.errorTarget) this.errorTarget.textContent = '';

      const formData = new FormData(this.form);
      const item = {
        id: Number(formData.get('id')),
        quantity: Number(formData.get('quantity') || 1)
      };

      const properties = {};
      formData.forEach((value, key) => {
        const match = key.match(/^properties\[(.+)\]$/);
        if (match && value) properties[match[1]] = value;
      });
      if (Object.keys(properties).length) item.properties = properties;

      const sellingPlan = formData.get('selling_plan');
      if (sellingPlan) item.selling_plan = Number(sellingPlan);

      try {
        await cart.add(item);
        this.setLoading(false);
        this.flashAdded();

        const image = this.dataset.productImage;
        const title = this.dataset.productTitle;

        if (!cart.openDrawer()) {
          toast(title ? `${title} — ${strings.added}` : strings.added, image);
        } else if (title) {
          toast(`${title} — ${strings.added}`, image);
        }
      } catch (error) {
        this.setLoading(false);
        const message = (error.data && error.data.description) || error.message;
        if (this.errorTarget) this.errorTarget.textContent = message;
        else toast(message);
      }
    }

    setLoading(loading) {
      if (!this.submitButton) return;
      this.submitButton.classList.toggle('is-loading', loading);
      this.submitButton.setAttribute('aria-disabled', loading ? 'true' : 'false');
    }

    flashAdded() {
      const label = this.submitButton && this.submitButton.querySelector('.button__label');
      if (!label) return;

      const original = label.textContent;
      label.textContent = strings.added;
      setTimeout(() => {
        label.textContent = original;
      }, 1600);
    }
  }

  customElements.define('product-form', ProductForm);

  /* Quantity stepper + cart line item quantity. */
  class QuantityInput extends HTMLElement {
    connectedCallback() {
      this.input = this.querySelector('input');
      if (!this.input) return;

      this.querySelectorAll('[data-quantity-button]').forEach((button) => {
        button.addEventListener('click', (event) => {
          event.preventDefault();
          const step = button.dataset.quantityButton === 'increase' ? 1 : -1;
          const min = Number(this.input.min || 0);
          const next = Math.max(min, Number(this.input.value || 0) + step);
          if (next === Number(this.input.value)) return;

          this.input.value = next;
          this.input.dispatchEvent(new Event('change', { bubbles: true }));
        });
      });
    }
  }

  customElements.define('quantity-input', QuantityInput);

  /* Cart line item mutations (quantity change / remove). */
  class CartItems extends HTMLElement {
    connectedCallback() {
      this.addEventListener('change', (event) => {
        const input = event.target.closest('[data-cart-quantity]');
        if (!input) return;
        this.updateLine(input.dataset.line, Number(input.value), input);
      });

      this.addEventListener('click', (event) => {
        const remove = event.target.closest('[data-cart-remove]');
        if (!remove) return;
        event.preventDefault();
        this.updateLine(remove.dataset.line, 0, remove);
      });
    }

    async updateLine(line, quantity, source) {
      const row = source.closest('[data-cart-item]');
      if (row) row.classList.add('is-removing');
      this.classList.add('is-loading');

      try {
        await cart.change({ line: Number(line), quantity });
      } catch (error) {
        if (row) row.classList.remove('is-removing');
        toast(error.message);
      } finally {
        this.classList.remove('is-loading');
      }
    }
  }

  customElements.define('cart-items', CartItems);

  /* Free shipping progress bar. */
  class ShippingBar extends HTMLElement {
    connectedCallback() {
      this.render(Number(this.dataset.total || 0));
      document.addEventListener('cart:updated', (event) => this.render(event.detail.cart.total_price));
    }

    render(totalCents) {
      const threshold = Number(settings.freeShippingThreshold || 0) * 100;
      if (threshold <= 0) {
        this.hidden = true;
        return;
      }

      this.hidden = false;
      const remaining = Math.max(0, threshold - totalCents);
      const progress = Math.min(100, (totalCents / threshold) * 100);

      const textTarget = this.querySelector('[data-shipping-text]');
      const fill = this.querySelector('[data-shipping-fill]');

      if (fill) fill.style.setProperty('--progress', `${progress}%`);
      this.classList.toggle('shipping-bar--qualified', remaining === 0);

      if (!textTarget) return;

      if (remaining === 0) {
        textTarget.textContent = strings.shippingQualified;
      } else {
        const template = strings.shippingProgress || 'You are [[amount]] away from free shipping.';
        const [before, after] = template.split('[[amount]]');
        textTarget.textContent = '';
        textTarget.append(document.createTextNode(before || ''));
        const strong = document.createElement('strong');
        strong.textContent = formatMoney(remaining);
        textTarget.append(strong, document.createTextNode(after || ''));
      }
    }
  }

  customElements.define('shipping-bar', ShippingBar);

  /* Discount code — applied through the /discount route, then cart re-renders. */
  class CartDiscount extends HTMLElement {
    connectedCallback() {
      this.toggle = this.querySelector('[data-discount-toggle]');
      this.form = this.querySelector('[data-discount-form]');
      this.input = this.querySelector('input');
      this.message = this.querySelector('[data-discount-message]');

      if (this.toggle && this.form) {
        this.form.hidden = true;
        this.toggle.addEventListener('click', () => {
          this.form.hidden = !this.form.hidden;
          if (!this.form.hidden && this.input) this.input.focus();
        });
      }

      if (this.form) this.form.addEventListener('submit', (event) => this.apply(event));
    }

    async apply(event) {
      event.preventDefault();
      const code = (this.input.value || '').trim();
      if (!code) return;

      const button = this.form.querySelector('[type="submit"]');
      if (button) button.classList.add('is-loading');
      if (this.message) this.message.textContent = '';

      try {
        // Shopify applies the code to the cart session on this route.
        const response = await fetch(`${routes.root}discount/${encodeURIComponent(code)}`, {
          method: 'GET',
          headers: { Accept: 'text/html' }
        });
        if (!response.ok) throw new Error(strings.discountError);

        const state = await cart.fetchState();
        const applied = (state.cart_level_discount_applications || []).some(
          (discount) => (discount.title || '').toUpperCase() === code.toUpperCase()
        );

        // Re-render regardless so line-level discounts appear too.
        await cart.update({ attributes: state.attributes || {} });

        if (!applied && !(state.cart_level_discount_applications || []).length) {
          if (this.message) this.message.textContent = strings.discountError;
        } else if (this.input) {
          this.input.value = '';
        }
      } catch (error) {
        if (this.message) this.message.textContent = error.message || strings.discountError;
      } finally {
        if (button) button.classList.remove('is-loading');
      }
    }
  }

  customElements.define('cart-discount', CartDiscount);

  /* Cart note. */
  class CartNote extends HTMLElement {
    connectedCallback() {
      const textarea = this.querySelector('textarea');
      if (!textarea) return;

      textarea.addEventListener(
        'change',
        debounce(() => {
          cart.update({ note: textarea.value }).catch(() => {});
        }, 400)
      );
    }
  }

  customElements.define('cart-note', CartNote);

  /* Header cart bubble — kept in sync without re-rendering the header. */
  class CartCount extends HTMLElement {
    connectedCallback() {
      this.render(Number(this.dataset.count || 0));
      document.addEventListener('cart:updated', (event) => this.render(event.detail.cart.item_count));
    }

    render(count) {
      this.textContent = count > 99 ? '99+' : count || '';
      this.classList.toggle('is-visible', count > 0);

      const label = this.closest('[data-cart-link]');
      if (label) {
        label.setAttribute(
          'aria-label',
          `${strings.cartLabel || 'Cart'}${count ? ` (${count})` : ''}`
        );
      }
    }
  }

  customElements.define('cart-count', CartCount);

  /* Cart drawer opens itself whenever an item is added. */
  class CartDrawer extends OverlayElement {
    connectedCallback() {
      super.connectedCallback();
      this.setAttribute('aria-hidden', 'true');
    }
  }

  customElements.define('cart-drawer', CartDrawer);

  /* ------------------------------------------------------------------------
     Variant selector
     ------------------------------------------------------------------------ */

  class VariantPicker extends HTMLElement {
    connectedCallback() {
      this.section = this.closest('[data-section-id]');
      this.productHandle = this.dataset.productHandle;
      this.variants = this.readVariants();

      this.addEventListener('change', () => this.onChange());
    }

    readVariants() {
      const script = this.querySelector('[data-variant-json]');
      if (!script) return [];
      try {
        return JSON.parse(script.textContent);
      } catch (error) {
        return [];
      }
    }

    get selectedOptions() {
      return Array.from(this.querySelectorAll('.variant-option')).map((group) => {
        const checked = group.querySelector('input:checked');
        return checked ? checked.value : null;
      });
    }

    onChange() {
      const selected = this.selectedOptions;

      this.querySelectorAll('.variant-option').forEach((group) => {
        const label = group.querySelector('[data-selected-value]');
        const checked = group.querySelector('input:checked');
        if (label && checked) label.textContent = checked.value;
      });

      const variant = this.variants.find((candidate) =>
        candidate.options.every((option, index) => option === selected[index])
      );

      this.updateAvailability(selected);
      this.updateUrl(variant);
      this.updateIdInput(variant);
      this.updatePrice(variant);
      this.updateMedia(variant);
      this.updateButton(variant);

      publish('variant:changed', { variant, section: this.section });
    }

    /* Grey out values that cannot be reached from the current selection.
       For each option group we hold every *other* selected option fixed and
       ask whether any in-stock variant exists with this value. */
    updateAvailability(selected) {
      this.querySelectorAll('.variant-option').forEach((group, groupIndex) => {
        group.querySelectorAll('input').forEach((input) => {
          const available = this.variants.some((variant) => {
            if (variant.options[groupIndex] !== input.value) return false;

            const otherOptionsMatch = selected.every(
              (option, index) => index === groupIndex || option === null || variant.options[index] === option
            );

            return otherOptionsMatch && variant.available;
          });

          const label = group.querySelector(`label[for="${input.id}"]`);
          if (label) label.classList.toggle('variant-option__value--unavailable', !available);

          if (available) input.removeAttribute('aria-describedby');
          else input.setAttribute('aria-describedby', 'variant-unavailable');
        });
      });
    }

    updateUrl(variant) {
      if (!variant || this.dataset.updateUrl === 'false') return;
      window.history.replaceState({}, '', `${this.dataset.productUrl}?variant=${variant.id}`);
    }

    updateIdInput(variant) {
      document.querySelectorAll(`[data-variant-id-input="${this.dataset.sectionId}"]`).forEach((input) => {
        input.value = variant ? variant.id : '';
        input.dispatchEvent(new Event('change', { bubbles: true }));
      });
    }

    updatePrice(variant) {
      const target = document.querySelector(`[data-variant-price="${this.dataset.sectionId}"]`);
      if (!target) return;

      if (!variant) {
        target.innerHTML = '';
        return;
      }

      const onSale = variant.compare_at_price && variant.compare_at_price > variant.price;
      const parts = [`<span class="price__current">${formatMoney(variant.price)}</span>`];
      if (onSale) parts.push(`<s class="price__compare">${formatMoney(variant.compare_at_price)}</s>`);

      target.innerHTML = parts.join('');
      target.classList.toggle('price--on-sale', Boolean(onSale));
    }

    updateMedia(variant) {
      if (!variant || !variant.featured_media) return;

      const gallery = document.querySelector(`[data-product-gallery="${this.dataset.sectionId}"]`);
      if (!gallery) return;

      const slide = gallery.querySelector(`[data-media-id="${variant.featured_media.id}"]`);
      if (!slide) return;

      if (gallery.classList.contains('product__gallery--carousel')) {
        const slides = slide.parentElement;
        slides.scrollTo({ left: slide.offsetLeft - slides.offsetLeft, behavior: motionOK() ? 'smooth' : 'auto' });
      } else {
        slide.scrollIntoView({ behavior: motionOK() ? 'smooth' : 'auto', block: 'nearest' });
      }
    }

    updateButton(variant) {
      const button = document.querySelector(`[data-add-button="${this.dataset.sectionId}"]`);
      if (!button) return;

      const label = button.querySelector('.button__label');
      const unavailable = !variant;
      const soldOut = variant && !variant.available;

      button.setAttribute('aria-disabled', unavailable || soldOut ? 'true' : 'false');
      button.disabled = Boolean(unavailable || soldOut);

      if (!label) return;
      if (unavailable) label.textContent = strings.unavailable;
      else if (soldOut) label.textContent = strings.soldOut;
      else label.textContent = strings.addToCart;
    }
  }

  customElements.define('variant-picker', VariantPicker);

  /* ------------------------------------------------------------------------
     Product gallery — thumbs, carousel sync, zoom
     ------------------------------------------------------------------------ */

  class ProductGallery extends HTMLElement {
    connectedCallback() {
      this.slides = this.querySelector('[data-gallery-slides]');
      this.thumbs = Array.from(this.querySelectorAll('[data-gallery-thumb]'));
      this.zoomEnabled = this.dataset.zoom === 'true';

      this.thumbs.forEach((thumb) => {
        thumb.addEventListener('click', (event) => {
          event.preventDefault();
          this.goTo(thumb.dataset.galleryThumb);
        });
      });

      if (this.slides) {
        this.slides.addEventListener('scroll', debounce(() => this.syncThumbs(), 120), { passive: true });
      }

      if (this.zoomEnabled) this.initZoom();
    }

    goTo(mediaId) {
      const slide = this.querySelector(`[data-media-id="${mediaId}"]`);
      if (!slide) return;

      if (this.slides) {
        this.slides.scrollTo({
          left: slide.offsetLeft - this.slides.offsetLeft,
          behavior: motionOK() ? 'smooth' : 'auto'
        });
      } else {
        slide.scrollIntoView({ behavior: motionOK() ? 'smooth' : 'auto', block: 'center' });
      }

      this.setCurrent(mediaId);
    }

    syncThumbs() {
      if (!this.slides) return;

      const center = this.slides.scrollLeft + this.slides.clientWidth / 2;
      let closest = null;
      let closestDistance = Infinity;

      Array.from(this.slides.children).forEach((slide) => {
        const slideCenter = slide.offsetLeft - this.slides.offsetLeft + slide.clientWidth / 2;
        const distance = Math.abs(slideCenter - center);
        if (distance < closestDistance) {
          closestDistance = distance;
          closest = slide;
        }
      });

      if (closest) this.setCurrent(closest.dataset.mediaId);
    }

    setCurrent(mediaId) {
      this.thumbs.forEach((thumb) => {
        thumb.setAttribute('aria-current', thumb.dataset.galleryThumb === String(mediaId) ? 'true' : 'false');
      });
    }

    /* Hover-tracked magnify on desktop, tap-to-lightbox on touch. */
    initZoom() {
      const lightbox = document.querySelector('[data-zoom-lightbox]');
      const canHover = window.matchMedia('(hover: hover) and (pointer: fine)').matches;

      this.querySelectorAll('.product__media-item--zoomable').forEach((item) => {
        const img = item.querySelector('img');
        if (!img) return;

        if (canHover) {
          item.addEventListener('pointerenter', () => item.classList.add('is-zoomed'));
          item.addEventListener('pointerleave', () => {
            item.classList.remove('is-zoomed');
            img.style.transformOrigin = 'center';
          });
          item.addEventListener(
            'pointermove',
            (event) => {
              const rect = item.getBoundingClientRect();
              const x = ((event.clientX - rect.left) / rect.width) * 100;
              const y = ((event.clientY - rect.top) / rect.height) * 100;
              img.style.transformOrigin = `${x}% ${y}%`;
            },
            { passive: true }
          );
        }

        item.addEventListener('click', (event) => {
          if (!lightbox) return;
          event.preventDefault();

          const full = lightbox.querySelector('img');
          full.src = img.dataset.zoomSrc || img.currentSrc || img.src;
          full.alt = img.alt || '';
          lightbox.open();
        });
      });
    }
  }

  customElements.define('product-gallery', ProductGallery);

  class ZoomLightbox extends OverlayElement {
    connectedCallback() {
      super.connectedCallback();
      this.addEventListener('click', () => this.close());
    }
  }

  customElements.define('zoom-lightbox', ZoomLightbox);

  /* ------------------------------------------------------------------------
     Quick view
     ------------------------------------------------------------------------ */

  class QuickView extends OverlayElement {
    connectedCallback() {
      super.connectedCallback();
      this.body = this.querySelector('[data-quick-view-body]');
      this.skeleton = this.querySelector('[data-quick-view-skeleton]');

      document.addEventListener('click', (event) => {
        const trigger = event.target.closest('[data-quick-view]');
        if (!trigger) return;
        event.preventDefault();
        this.load(trigger.dataset.quickView, trigger);
      });
    }

    async load(url, trigger) {
      this.open(trigger);
      if (this.body) this.body.innerHTML = '';
      if (this.skeleton) this.skeleton.hidden = false;

      try {
        const response = await fetch(`${url}${url.includes('?') ? '&' : '?'}view=quick-view`);
        if (!response.ok) throw new Error('Unable to load product');

        const markup = await response.text();
        const doc = new DOMParser().parseFromString(markup, 'text/html');
        const content = doc.querySelector('[data-quick-view-content]');

        if (this.skeleton) this.skeleton.hidden = true;
        if (content && this.body) {
          // Custom elements in the fragment upgrade themselves on insertion.
          this.body.innerHTML = content.innerHTML;
          initImageLoading(this.body);
          syncFieldLabels(this.body);
        }
      } catch (error) {
        if (this.skeleton) this.skeleton.hidden = true;
        if (this.body) this.body.innerHTML = `<p class="text-body">${error.message}</p>`;
      }
    }
  }

  customElements.define('quick-view-modal', QuickView);

  /* ------------------------------------------------------------------------
     Wishlist — localStorage, no account required
     ------------------------------------------------------------------------ */

  const wishlist = {
    key: 'atelier:wishlist',

    read() {
      try {
        const raw = localStorage.getItem(this.key);
        const parsed = raw ? JSON.parse(raw) : [];
        return Array.isArray(parsed) ? parsed : [];
      } catch (error) {
        return [];
      }
    },

    write(handles) {
      try {
        localStorage.setItem(this.key, JSON.stringify(handles.slice(0, 100)));
      } catch (error) {
        /* Storage may be unavailable in private mode — fail quietly. */
      }
      publish('wishlist:updated', { handles });
    },

    has(handle) {
      return this.read().includes(handle);
    },

    toggle(handle) {
      const handles = this.read();
      const index = handles.indexOf(handle);

      if (index > -1) handles.splice(index, 1);
      else handles.unshift(handle);

      this.write(handles);
      return index === -1;
    }
  };

  class WishlistToggle extends HTMLElement {
    connectedCallback() {
      this.button = this.querySelector('button') || this;
      this.handle = this.dataset.handle;
      this.sync();

      this.button.addEventListener('click', (event) => {
        event.preventDefault();
        const added = wishlist.toggle(this.handle);
        this.sync();
        toast(added ? strings.wishlistAdd : strings.wishlistRemove);
      });

      document.addEventListener('wishlist:updated', () => this.sync());
    }

    sync() {
      const active = wishlist.has(this.handle);
      this.button.setAttribute('aria-pressed', active ? 'true' : 'false');
      this.button.setAttribute('aria-label', active ? strings.wishlistRemove : strings.wishlistAdd);
    }
  }

  customElements.define('wishlist-toggle', WishlistToggle);

  class WishlistCount extends HTMLElement {
    connectedCallback() {
      this.render();
      document.addEventListener('wishlist:updated', () => this.render());
    }

    render() {
      const count = wishlist.read().length;
      this.textContent = count > 0 ? count : '';
      this.classList.toggle('is-visible', count > 0);
    }
  }

  customElements.define('wishlist-count', WishlistCount);

  class WishlistDrawer extends OverlayElement {
    connectedCallback() {
      super.connectedCallback();
      this.list = this.querySelector('[data-wishlist-list]');
      this.empty = this.querySelector('[data-wishlist-empty]');
      document.addEventListener('wishlist:updated', () => {
        if (this.isOpen) this.render();
      });
    }

    open(trigger) {
      super.open(trigger);
      this.render();
    }

    async render() {
      const handles = wishlist.read();

      if (!handles.length) {
        if (this.list) this.list.innerHTML = '';
        if (this.empty) this.empty.hidden = false;
        return;
      }

      if (this.empty) this.empty.hidden = true;
      if (!this.list) return;

      this.list.innerHTML = '<div class="drawer__empty"><span class="spinner"></span></div>';

      const cards = await Promise.all(
        handles.map(async (handle) => {
          try {
            const response = await fetch(`${routes.root}products/${handle}?view=card`);
            if (!response.ok) return '';
            const markup = await response.text();
            const doc = new DOMParser().parseFromString(markup, 'text/html');
            const card = doc.querySelector('[data-wishlist-card]');
            return card ? card.outerHTML : '';
          } catch (error) {
            return '';
          }
        })
      );

      this.list.innerHTML = cards.filter(Boolean).join('') || '';
      initImageLoading(this.list);

      if (!this.list.children.length && this.empty) this.empty.hidden = false;
    }
  }

  customElements.define('wishlist-drawer', WishlistDrawer);

  /* ------------------------------------------------------------------------
     Product recommendations — fetched lazily, only when scrolled near
     ------------------------------------------------------------------------ */

  class ProductRecommendations extends HTMLElement {
    connectedCallback() {
      if (this.children.length || !this.dataset.url) return;

      const load = () => this.load();

      if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver(
          (entries) => {
            if (!entries[0].isIntersecting) return;
            observer.disconnect();
            load();
          },
          { rootMargin: '600px 0px' }
        );
        observer.observe(this);
      } else {
        load();
      }
    }

    async load() {
      try {
        const response = await fetch(this.dataset.url);
        if (!response.ok) throw new Error('unavailable');

        const markup = await response.text();
        const doc = new DOMParser().parseFromString(markup, 'text/html');
        const source = doc.querySelector('product-recommendations');

        if (!source || !source.innerHTML.trim()) {
          this.hidden = true;
          return;
        }

        this.innerHTML = source.innerHTML;
        boot(this);
      } catch (error) {
        this.hidden = true;
      }
    }
  }

  customElements.define('product-recommendations', ProductRecommendations);

  /* ------------------------------------------------------------------------
     Recently viewed — localStorage list rendered through the search endpoint
     ------------------------------------------------------------------------ */

  const recentlyViewed = {
    key: 'atelier:recently-viewed',

    read() {
      try {
        const raw = localStorage.getItem(this.key);
        const parsed = raw ? JSON.parse(raw) : [];
        return Array.isArray(parsed) ? parsed : [];
      } catch (error) {
        return [];
      }
    },

    push(handle) {
      if (!handle) return;
      const handles = this.read().filter((item) => item !== handle);
      handles.unshift(handle);

      try {
        localStorage.setItem(this.key, JSON.stringify(handles.slice(0, 12)));
      } catch (error) {
        /* no-op */
      }
    }
  };

  class RecentlyViewed extends HTMLElement {
    async connectedCallback() {
      const current = this.dataset.currentProduct || '';
      const handles = recentlyViewed.read().filter((handle) => handle !== current);
      const limit = Number(this.dataset.limit || 4);
      const selected = handles.slice(0, limit);

      if (!selected.length) {
        this.hidden = true;
        return;
      }

      // One search request covers every handle, so this stays a single round trip.
      const query = selected.map((handle) => `handle:${handle}`).join(' OR ');
      const params = new URLSearchParams({
        q: query,
        type: 'product',
        section_id: this.dataset.sectionId || 'recently-viewed-results'
      });

      try {
        const response = await fetch(`${routes.search}?${params}`);
        if (!response.ok) throw new Error('unavailable');

        const markup = await response.text();
        const doc = new DOMParser().parseFromString(markup, 'text/html');
        const grid = doc.querySelector('[data-recently-viewed-grid]');
        const target = this.querySelector('[data-recently-viewed-target]');

        if (!grid || !grid.children.length || !target) {
          this.hidden = true;
          return;
        }

        target.innerHTML = grid.innerHTML;
        this.hidden = false;
        initImageLoading(this);
        observeReveals(this);
      } catch (error) {
        this.hidden = true;
      }
    }
  }

  customElements.define('recently-viewed', RecentlyViewed);

  /* ------------------------------------------------------------------------
     Facets — filter and sort without a full page load
     ------------------------------------------------------------------------ */

  class FacetFilters extends HTMLElement {
    connectedCallback() {
      this.form = this.querySelector('form');
      this.results = document.querySelector('[data-collection-results]');
      if (!this.form) return;

      this.form.addEventListener('input', (event) => {
        if (event.target.type === 'text' || event.target.type === 'number') return;
        this.apply();
      });

      this.form.addEventListener('change', (event) => {
        if (event.target.matches('[data-sort]')) this.apply();
      });

      this.form.addEventListener('submit', (event) => {
        event.preventDefault();
        this.apply();
      });

      this.addEventListener('click', (event) => {
        const clear = event.target.closest('[data-facet-clear]');
        if (!clear) return;
        event.preventDefault();
        this.navigate(clear.getAttribute('href') || window.location.pathname);
      });

      window.addEventListener('popstate', () => this.navigate(window.location.href, false));
    }

    apply() {
      const params = new URLSearchParams(new FormData(this.form));
      // Drop empty values so URLs stay clean and shareable.
      Array.from(params.keys()).forEach((key) => {
        if (!params.get(key)) params.delete(key);
      });

      const url = `${window.location.pathname}?${params.toString()}`;
      this.navigate(url);
    }

    async navigate(url, pushState = true) {
      if (this.results) this.results.classList.add('is-loading');

      try {
        const response = await fetch(url);
        if (!response.ok) throw new Error('Unable to filter');

        const markup = await response.text();
        const doc = new DOMParser().parseFromString(markup, 'text/html');

        const newResults = doc.querySelector('[data-collection-results]');
        if (newResults && this.results) this.results.innerHTML = newResults.innerHTML;

        const newFacets = doc.querySelector('facet-filters');
        if (newFacets) {
          const openPanels = Array.from(this.querySelectorAll('.facet[open]')).map((el) => el.dataset.facetId);
          this.innerHTML = newFacets.innerHTML;
          this.form = this.querySelector('form');
          openPanels.forEach((id) => {
            const facet = this.querySelector(`.facet[data-facet-id="${id}"]`);
            if (facet) facet.open = true;
          });
        }

        if (pushState) window.history.pushState({}, '', url);

        initImageLoading(this.results || document);
        observeReveals(this.results || document);

        const heading = document.querySelector('[data-collection-anchor]');
        if (heading) {
          const header = document.querySelector('.header');
          const offset = (header ? header.offsetHeight : 0) + 90;
          const top = heading.getBoundingClientRect().top + window.scrollY - offset;
          if (window.scrollY > top) window.scrollTo({ top, behavior: motionOK() ? 'smooth' : 'auto' });
        }
      } catch (error) {
        window.location.href = url;
      } finally {
        if (this.results) this.results.classList.remove('is-loading');
      }
    }
  }

  customElements.define('facet-filters', FacetFilters);

  /* ------------------------------------------------------------------------
     Announcement bar rotator
     ------------------------------------------------------------------------ */

  class AnnouncementBar extends HTMLElement {
    connectedCallback() {
      const dismissKey = 'atelier:announcement-dismissed';
      const closeButton = this.querySelector('[data-announcement-close]');

      if (closeButton) {
        try {
          if (sessionStorage.getItem(dismissKey) === this.dataset.version) {
            this.hidden = true;
            return;
          }
        } catch (error) {
          /* no-op */
        }

        closeButton.addEventListener('click', () => {
          this.hidden = true;
          try {
            sessionStorage.setItem(dismissKey, this.dataset.version);
          } catch (error) {
            /* no-op */
          }
        });
      }

      const items = Array.from(this.querySelectorAll('.announcement__item'));
      if (items.length < 2 || this.dataset.rotate !== 'true') return;

      const interval = Number(this.dataset.rotateSpeed || 5) * 1000;
      let index = 0;

      setInterval(() => {
        items[index].classList.remove('is-active');
        index = (index + 1) % items.length;
        items[index].classList.add('is-active');
      }, interval);
    }
  }

  customElements.define('announcement-bar', AnnouncementBar);

  /* ------------------------------------------------------------------------
     Accordion — animated open/close that keeps native <details> semantics
     ------------------------------------------------------------------------ */

  class AccordionItem extends HTMLElement {
    connectedCallback() {
      this.details = this.querySelector('details') || this.closest('details');
      if (!this.details) return;

      this.summary = this.details.querySelector('summary');
      this.content = this.details.querySelector('.accordion__content');
      if (!this.summary || !this.content) return;

      this.summary.addEventListener('click', (event) => {
        if (!motionOK()) return;
        event.preventDefault();
        this.details.open ? this.collapse() : this.expand();
      });
    }

    expand() {
      this.details.open = true;
      const height = this.content.scrollHeight;
      this.animate(0, height);
    }

    collapse() {
      const height = this.content.scrollHeight;
      const animation = this.animate(height, 0);
      animation.addEventListener('finish', () => {
        this.details.open = false;
      });
    }

    animate(from, to) {
      const animation = this.content.animate(
        { height: [`${from}px`, `${to}px`], opacity: [from ? 1 : 0, to ? 1 : 0] },
        { duration: 320, easing: 'cubic-bezier(0.22, 0.61, 0.36, 1)' }
      );
      animation.addEventListener('finish', () => {
        this.content.style.height = '';
      });
      return animation;
    }
  }

  customElements.define('accordion-item', AccordionItem);

  /* ------------------------------------------------------------------------
     Newsletter inline feedback
     ------------------------------------------------------------------------ */

  document.querySelectorAll('[data-newsletter-form]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      const input = form.querySelector('input[type="email"]');
      const message = form.querySelector('[data-newsletter-message]');
      const value = input ? input.value.trim() : '';

      if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value)) {
        event.preventDefault();
        if (message) {
          message.textContent = form.dataset.errorMessage || '';
          message.classList.add('form__message--error');
        }
        if (input) input.focus();
      }
    });
  });

  /* ------------------------------------------------------------------------
     Floating-label state for fields that are pre-filled by the browser
     ------------------------------------------------------------------------ */

  const syncFieldLabels = (root = document) => {
    root.querySelectorAll('.field__input').forEach((input) => {
      const sync = () => input.classList.toggle('has-value', Boolean(input.value));
      sync();
      if (!input.dataset.labelBound) {
        input.dataset.labelBound = 'true';
        input.addEventListener('input', sync);
        input.addEventListener('change', sync);
      }
    });
  };

  /* ------------------------------------------------------------------------
     Share / copy link
     ------------------------------------------------------------------------ */

  document.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-copy-link]');
    if (!button) return;

    event.preventDefault();
    const url = button.dataset.copyLink || window.location.href;

    try {
      if (navigator.share && window.matchMedia('(pointer: coarse)').matches) {
        await navigator.share({ url, title: document.title });
      } else {
        await navigator.clipboard.writeText(url);
        toast(strings.copied);
      }
    } catch (error) {
      /* User dismissed the share sheet — nothing to report. */
    }
  });

  /* ------------------------------------------------------------------------
     Boot
     ------------------------------------------------------------------------ */

  const boot = (root = document) => {
    buildTextReveals(root);
    observeReveals(root);
    initImageLoading(root);
    syncFieldLabels(root);
    parallax.register(root);
  };

  const init = () => {
    boot();
    initCursor();
    initPageTransition();

    const handle = document.body.dataset.productHandle;
    if (handle) recentlyViewed.push(handle);

    // Cart drawer opens on add, unless the section rendered a page-level cart.
    document.addEventListener('cart:updated', () => {
      parallax.refresh();
    });
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }

  // Shopify theme editor: re-initialise sections as they are added or reloaded.
  document.addEventListener('shopify:section:load', (event) => {
    boot(event.target);
    parallax.refresh();
  });

  document.addEventListener('shopify:section:unload', () => parallax.refresh());
  document.addEventListener('shopify:section:select', (event) => boot(event.target));

  prefersReducedMotion.addEventListener('change', () => {
    if (!motionOK()) {
      document.querySelectorAll('[data-reveal]').forEach((el) => el.classList.add('is-revealed'));
    }
  });

  // Expose a small surface for apps and custom snippets.
  window.Atelier = { cart, wishlist, recentlyViewed, toast, formatMoney, boot };
})();
