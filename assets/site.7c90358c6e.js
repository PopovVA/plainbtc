(()=>{const menus=document.querySelectorAll("details.lang-menu");if(menus.length){const closeAll=e=>{menus.forEach(m=>{if(m!==e)m.open=false})};document.addEventListener("click",e=>{menus.forEach(m=>{if(m.open&&!m.contains(e.target))m.open=false})});document.addEventListener("keydown",e=>{if(e.key==="Escape")closeAll()});menus.forEach(m=>{m.addEventListener("toggle",()=>{if(m.open)closeAll(m)})})}try{if(navigator.webdriver)return;const ua=navigator.userAgent||"";if(/bot|crawl|spider|slurp|bingpreview|facebookexternalhit|embedly|quora|pinterest|redditbot|whatsapp|telegram|discordbot|preview|headless|lighthouse|pagespeed/i.test(ua))return;const u=new URL(location.href);let rh="";try{if(document.referrer)rh=new URL(document.referrer).hostname}catch(_){}const w=window.innerWidth||0;const body=JSON.stringify({path:u.pathname||"/",lang:(document.documentElement.lang||"en").slice(0,16),referrer_host:rh.slice(0,253),utm_source:(u.searchParams.get("utm_source")||"").slice(0,64),utm_medium:(u.searchParams.get("utm_medium")||"").slice(0,64),utm_campaign:(u.searchParams.get("utm_campaign")||"").slice(0,128),device:w<768?"mobile":w<1024?"tablet":"desktop"});if(navigator.sendBeacon)navigator.sendBeacon("/api/hit",new Blob([body],{type:"application/json"}));else fetch("/api/hit",{method:"POST",body,headers:{"content-type":"application/json"},keepalive:true}).catch(()=>{})}catch(_){}})();
(()=>{const f=document.querySelector("form.newsletter-form");if(!f)return;const st=f.parentElement.querySelector(".nl-status");const btn=f.querySelector("button");const src=f.querySelector('input[name="source"]');if(src&&!src.value)src.value=location.pathname;const show=(t,ok)=>{st.textContent=t;st.className="nl-status "+(ok?"ok":"err")};f.addEventListener("submit",async e=>{e.preventDefault();const em=f.elements.email;if(!em.value||!em.checkValidity()){show(f.dataset.invalid,false);em.focus();return}const label=btn.textContent;btn.disabled=true;btn.textContent=f.dataset.sending;try{const r=await fetch(f.action,{method:"POST",headers:{Accept:"application/json"},body:new FormData(f)});let j={};try{j=await r.json()}catch(_){}if(r.ok&&j.status==="ok"){show(f.dataset.ok,true);em.value=""}else if(r.status===429)show(f.dataset.rate,false);else if(r.status===400)show(f.dataset.invalid,false);else show(f.dataset.error,false)}catch(_){show(f.dataset.error,false)}finally{btn.disabled=false;btn.textContent=label}})})();
(()=>{try{const partnerOf=a=>{const d=a.getAttribute("data-partner");if(d)return d.slice(0,32);const h=a.href||"";if(/coinbase\.com\/join/i.test(h))return"coinbase";if(/gemini\.com/i.test(h))return"gemini";if(/river\.com/i.test(h))return"river";if(/uphold\.com/i.test(h))return"uphold";return""};const send=a=>{const partner=partnerOf(a);if(!partner)return;const u=new URL(location.href);let rh="";try{if(document.referrer)rh=new URL(document.referrer).hostname}catch(_){}const body=JSON.stringify({partner,path:u.pathname||"/",lang:(document.documentElement.lang||"en").slice(0,16),referrer_host:rh.slice(0,253),utm_source:(u.searchParams.get("utm_source")||"").slice(0,64)});if(navigator.sendBeacon)navigator.sendBeacon("/api/click",new Blob([body],{type:"application/json"}));else fetch("/api/click",{method:"POST",body,headers:{"content-type":"application/json"},keepalive:true}).catch(()=>{})};document.addEventListener("click",e=>{const t=e.target;if(!t||!t.closest)return;const a=t.closest("a[data-partner], a[rel~='sponsored']");if(a)send(a)},true)}catch(_){}})();

/* ---------------------------------------------------------------------------------------------
   Interface: theme switch, scroll motion and reading aids. No dependencies.
   Everything here is an enhancement: pages read and navigate the same without it, and
   prefers-reduced-motion turns the animated parts off. Source of truth is assets/site.js;
   tools/build_i18n.py publishes it as assets/site.<hash>.js.
   --------------------------------------------------------------------------------------------- */
(() => {
  const root = document.documentElement;
  const mq = (q) => window.matchMedia(q);
  const reduce = mq("(prefers-reduced-motion: reduce)").matches;
  const fine = mq("(hover: hover) and (pointer: fine)").matches;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const header = $(".site-header");
  const scrollJobs = [];

  /* ---- light / dark theme (saved choice is applied before first paint by the inline head script) */
  const themeBtn = $(".theme-toggle");
  if (themeBtn) {
    const current = () => root.dataset.theme || (mq("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const paint = (t) => {
      themeBtn.setAttribute("aria-pressed", String(t === "dark"));
      $$('meta[name="theme-color"]').forEach((m) => { m.content = t === "dark" ? "#080e1d" : "#f4efe4"; });
    };
    const apply = (t) => {
      root.dataset.theme = t;
      try { localStorage.setItem("plainbtc-theme", t); } catch (_) {}
      paint(t);
    };
    themeBtn.hidden = false;
    if (root.dataset.theme) paint(root.dataset.theme);
    themeBtn.addEventListener("click", () => {
      const next = current() === "dark" ? "light" : "dark";
      if (reduce || !document.startViewTransition) return apply(next);
      const r = themeBtn.getBoundingClientRect();
      root.style.setProperty("--vt-x", `${r.left + r.width / 2}px`);
      root.style.setProperty("--vt-y", `${r.top + r.height / 2}px`);
      root.classList.add("theme-vt");
      document.startViewTransition(() => apply(next)).finished.finally(() => root.classList.remove("theme-vt"));
    });
  }

  /* ---- mobile menu: close on Escape or after picking a link */
  const navToggle = $("#nav-toggle");
  if (navToggle) {
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") navToggle.checked = false; });
    $$(".nav a").forEach((a) => a.addEventListener("click", () => { navToggle.checked = false; }));
  }

  /* ---- headline ticker: loop it (it is a plain scrollable list otherwise) */
  const ticker = $(".ticker");
  if (ticker && !reduce) {
    const track = $(".ticker-track", ticker);
    if (track && track.children.length > 2) {
      const copy = track.cloneNode(true);
      copy.setAttribute("aria-hidden", "true");
      $$("a", copy).forEach((a) => { a.tabIndex = -1; });
      track.after(copy);
      ticker.style.setProperty("--ticker-time", `${Math.max(30, Math.round(track.scrollWidth / 45))}s`);
      ticker.classList.add("is-live");
    }
  }

  /* ---- hero: noise on the left resolves into one plain line; the divider follows scroll and pointer */
  const art = $(".hero-art");
  if (art) {
    const svg = $(".wave", art), noise = $(".wave-noise", art), plain = $(".wave-plain", art);
    let w = 0, h = 0, lens = reduce ? 0.6 : 1, base = 0.6, target = 0.6, t = 0, raf = 0, seen = true, hovering = false;
    const rnd = (i) => { const x = Math.sin(i * 127.1) * 43758.5453; return x - Math.floor(x); };
    const vnoise = (x) => { const i = Math.floor(x), f = x - i, u = f * f * (3 - 2 * f); return (rnd(i) * (1 - u) + rnd(i + 1) * u) * 2 - 1; };
    const size = () => {
      const r = art.getBoundingClientRect();
      w = Math.max(1, r.width); h = Math.max(1, r.height);
      svg.setAttribute("viewBox", `0 0 ${w.toFixed(0)} ${h.toFixed(0)}`);
    };
    const draw = () => {
      lens += (target - lens) * 0.07;
      const lx = lens * w, mid = h / 2, step = 7, reach = Math.max(180, w * 0.3);
      let d = "";
      for (let x = 0; x < lx; x += step) {
        const amp = h * 0.42 * Math.pow(clamp((lx - x) / reach), 1.35);
        const n = vnoise(x * 0.11 + t * 2.1) * 0.62 + vnoise(x * 0.37 - t * 3.3) * 0.38;
        d += `${x ? "L" : "M"}${x.toFixed(1)} ${(mid + n * amp).toFixed(1)}`;
      }
      d += `${d ? "L" : "M"}${lx.toFixed(1)} ${mid.toFixed(1)}`;
      noise.setAttribute("d", d);
      plain.setAttribute("d", `M${lx.toFixed(1)} ${mid.toFixed(1)}H${w.toFixed(1)}`);
      art.style.setProperty("--lens", `${(lens * 100).toFixed(2)}%`);
    };
    const tick = () => { t += 0.011; draw(); raf = seen && !document.hidden ? requestAnimationFrame(tick) : 0; };
    const wake = () => { if (!raf && !reduce && seen && !document.hidden) raf = requestAnimationFrame(tick); };
    size(); draw();
    window.addEventListener("resize", () => { size(); draw(); }, { passive: true });
    if (!reduce) {
      if ("IntersectionObserver" in window) new IntersectionObserver((es) => { seen = es[0].isIntersecting; wake(); }).observe(art);
      document.addEventListener("visibilitychange", wake);
      scrollJobs.push((y) => { base = 0.6 - clamp(y / (window.innerHeight * 0.75)) * 0.4; if (!hovering) target = base; });
      if (fine) {
        art.addEventListener("pointermove", (e) => { hovering = true; target = clamp((e.clientX - art.getBoundingClientRect().left) / w, 0.06, 0.94); });
        art.addEventListener("pointerleave", () => { hovering = false; target = base; });
      }
      wake();
    } else { lens = target; draw(); }
  }

  /* ---- reveal on scroll (only elements that start below the fold) */
  if (!reduce && "IntersectionObserver" in window) {
    const sel = ".card, .guide-list li, .section-head, .loop > *, .about-box .disclosure, .article-figure, .takeaways, .mid-cta, .cta, .soft-guide, .content > .community-box, .content > .newsletter-box, .related, .sources";
    const vh = window.innerHeight;
    const items = $$(sel).filter((el) => el.getBoundingClientRect().top > vh * 0.92);
    if (items.length) {
      const io = new IntersectionObserver((entries) => {
        entries.forEach((en) => {
          if (!en.isIntersecting) return;
          const el = en.target;
          io.unobserve(el);
          el.classList.add("in");
          setTimeout(() => { el.classList.remove("reveal", "in"); el.style.removeProperty("--d"); }, 1500);
        });
      }, { rootMargin: "0px 0px -7% 0px", threshold: 0.05 });
      items.forEach((el) => {
        const sibs = el.parentElement ? Array.from(el.parentElement.children) : [];
        el.style.setProperty("--d", String(el.matches(".card, .guide-list li") ? sibs.indexOf(el) % 3 : 0));
        el.classList.add("reveal");
        io.observe(el);
      });
      root.classList.add("anim");
    }
  }

  /* ---- stats count up when they come into view */
  const counters = $$(".stat dd[data-count]");
  if (counters.length && !reduce && "IntersectionObserver" in window) {
    const run = (el) => {
      const end = Number(el.dataset.count) || 0, t0 = performance.now(), dur = 1200;
      const step = (now) => {
        const k = clamp((now - t0) / dur), e = 1 - Math.pow(1 - k, 4);
        el.textContent = String(Math.round(end * e));
        if (k < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    };
    const io = new IntersectionObserver((es) => es.forEach((en) => { if (en.isIntersecting) { io.unobserve(en.target); run(en.target); } }), { threshold: 0.6 });
    counters.forEach((el) => io.observe(el));
  }

  /* ---- pointer extras: spotlight that follows the cursor, slightly magnetic buttons */
  if (fine && !reduce) {
    document.addEventListener("pointermove", (e) => {
      const el = e.target.closest && e.target.closest(".card, .newsletter-box, .mid-cta, .cta");
      if (!el) return;
      const r = el.getBoundingClientRect();
      el.style.setProperty("--mx", `${e.clientX - r.left}px`);
      el.style.setProperty("--my", `${e.clientY - r.top}px`);
    }, { passive: true });
    $$(".btn, .cta-button, .newsletter-form button").forEach((b) => {
      b.addEventListener("pointermove", (e) => {
        const r = b.getBoundingClientRect();
        b.style.transform = `translate(${((e.clientX - r.left) / r.width - 0.5) * 10}px, ${((e.clientY - r.top) / r.height - 0.5) * 8}px)`;
      });
      b.addEventListener("pointerleave", () => { b.style.transform = ""; });
    });
  }

  /* ---- article pages: reading progress, table of contents, copy link, mobile newsletter bar */
  const main = $("main.article-page");
  const article = main && $("article.content", main);
  if (article) {
    let progress = 0;
    if (header) {
      const bar = document.createElement("span");
      bar.className = "progress";
      bar.setAttribute("aria-hidden", "true");
      bar.appendChild(document.createElement("i"));
      header.appendChild(bar);
      scrollJobs.push((y) => {
        const top = article.offsetTop, span = article.offsetHeight - window.innerHeight * 0.6;
        progress = clamp((y - top + 80) / Math.max(1, span));
        bar.style.setProperty("--p", progress.toFixed(4));
      });
    }

    const heads = $$(":scope > h2", article);
    if (heads.length >= 3) {
      const nav = document.createElement("nav");
      nav.className = "toc";
      nav.setAttribute("aria-label", main.dataset.toc || "On this page");
      const title = document.createElement("p");
      title.className = "toc-title";
      title.textContent = main.dataset.toc || "On this page";
      const ol = document.createElement("ol");
      const links = heads.map((hd, i) => {
        if (!hd.id) hd.id = `s-${i + 1}`;
        const a = document.createElement("a");
        a.href = `#${hd.id}`;
        a.textContent = hd.textContent;
        ol.appendChild(document.createElement("li")).appendChild(a);
        return a;
      });
      nav.append(title, ol);
      main.appendChild(nav);
      scrollJobs.push((y) => {
        const line = y + window.innerHeight * 0.3;
        let on = -1;
        heads.forEach((hd, i) => { if (hd.getBoundingClientRect().top + y <= line) on = i; });
        links.forEach((a, i) => a.classList.toggle("on", i === on));
        nav.classList.toggle("show", y > article.offsetTop + 260 && progress < 0.995);
      });
    }

    $$(".share-copy").forEach((b) => {
      if (!navigator.clipboard) return;
      b.hidden = false;
      const status = $(".share-status", b.parentElement);
      b.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(b.dataset.url || location.href);
          if (status) { status.textContent = b.dataset.copied || ""; setTimeout(() => { status.textContent = ""; }, 2400); }
        } catch (_) {}
      });
    });

    const box = $(".newsletter-box", article);
    let dismissed = false;
    try { dismissed = sessionStorage.getItem("plainbtc-nl-bar") === "1"; } catch (_) {}
    if (box && main.dataset.nl && !dismissed) {
      const bar = document.createElement("div");
      bar.className = "nl-bar";
      const text = document.createElement("span");
      text.textContent = main.dataset.nl;
      const go = document.createElement("a");
      go.href = "#nl-title";
      go.textContent = main.dataset.nlCta || "";
      const close = document.createElement("button");
      close.type = "button";
      close.setAttribute("aria-label", main.dataset.close || "Close");
      close.textContent = "×";
      bar.append(text, go, close);
      document.body.appendChild(bar);
      let boxSeen = false, closed = false;
      if ("IntersectionObserver" in window) new IntersectionObserver((es) => { boxSeen = es[0].isIntersecting; }).observe(box);
      const hide = () => { closed = true; bar.classList.remove("show"); try { sessionStorage.setItem("plainbtc-nl-bar", "1"); } catch (_) {} };
      close.addEventListener("click", hide);
      go.addEventListener("click", () => { hide(); setTimeout(() => { const em = $("#nl-email"); if (em) em.focus({ preventScroll: true }); }, 700); });
      scrollJobs.push(() => bar.classList.toggle("show", !closed && !boxSeen && progress > 0.28 && progress < 0.97));
    }
  }

  /* ---- one scroll listener for everything above */
  if (header) scrollJobs.push((y) => header.classList.toggle("is-stuck", y > 8));
  let queued = false;
  const onScroll = () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; const y = window.scrollY; scrollJobs.forEach((f) => f(y)); });
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll, { passive: true });
  onScroll();
})();
