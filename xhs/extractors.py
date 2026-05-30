from __future__ import annotations

EXTRACT_SEARCH_ITEMS_JS = r"""
() => {
  const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const absolutize = (href) => {
    if (!href) return "";
    try {
      return new URL(href, location.origin).href;
    } catch {
      return href;
    }
  };
  const visible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
  };
  const hrefScore = (anchor) => {
    const href = anchor.getAttribute("href") || "";
    let score = 0;
    if (href.includes("xsec_token=")) score += 100;
    if (anchor.matches("a.cover")) score += 30;
    if (anchor.matches("a.title")) score += 20;
    if (visible(anchor)) score += 10;
    if (href.includes("?")) score += 5;
    if ((anchor.getAttribute("style") || "").includes("display: none")) score -= 50;
    return score;
  };
  const noteHrefSelector = "a[href*='/explore/'], a[href*='/search_result/'][href*='xsec_token=']";
  const sections = Array.from(document.querySelectorAll("section.note-item, section[data-index]"));
  const cards = sections.length ? sections : Array.from(document.querySelectorAll(noteHrefSelector)).map((a) => a.closest("section") || a.parentElement);
  const seenCards = Array.from(new Set(cards.filter(Boolean)));

  return seenCards.map((section) => {
    const rect = section.getBoundingClientRect();
    const anchors = Array.from(section.querySelectorAll(noteHrefSelector));
    anchors.sort((a, b) => hrefScore(b) - hrefScore(a));
    const best = anchors[0];
    const titleEl = section.querySelector(".footer a.title, a.title, [class*='title']");
    const authorEl = section.querySelector(".author-wrapper a.author .name, a.author .name, .author-wrapper .name, [class*='author'] .name");
    const likeEl = section.querySelector(".like-wrapper .count, .count[selected-disabled-search], [class*='like'] .count");
    return {
      url: absolutize(best ? best.getAttribute("href") : ""),
      title: clean(titleEl ? titleEl.innerText || titleEl.textContent : ""),
      author_name: clean(authorEl ? authorEl.innerText || authorEl.textContent : ""),
      raw_liked_count: clean(likeEl ? likeEl.innerText || likeEl.textContent : ""),
      search_index: clean(section.getAttribute("data-index") || ""),
      viewport_top: rect.top,
      viewport_bottom: rect.bottom,
      document_top: rect.top + window.scrollY,
      document_bottom: rect.bottom + window.scrollY,
      viewport_height: window.innerHeight || document.documentElement.clientHeight || 0
    };
  }).filter((item) => item.url);
}
"""


EXTRACT_NOTE_JS = r"""
(noteId) => {
  const clean = (value) => {
    if (value === undefined || value === null) return "";
    return String(value).replace(/\s+/g, " ").trim();
  };

  const visibleText = (el) => {
    if (!el) return "";
    const style = window.getComputedStyle(el);
    if (style && (style.display === "none" || style.visibility === "hidden")) return "";
    return clean(el.innerText || el.textContent || "");
  };

  const uniqueElements = (items) => {
    const out = [];
    const seen = new Set();
    for (const item of items) {
      if (!item || seen.has(item)) continue;
      seen.add(item);
      out.push(item);
    }
    return out;
  };

  const detailRoots = (() => {
    const roots = [];
    const desc = document.querySelector("#detail-desc");
    if (desc) {
      roots.push(
        desc.closest("[class*='note-detail']"),
        desc.closest(".note-scroller"),
        desc.closest("[class*='detail']"),
        desc.closest("[class*='note-container']"),
        desc.closest("[class*='note']")
      );
    }
    for (const selector of [
      "#noteContainer",
      ".note-scroller",
      "[class*='note-detail']",
      "[class*='detail-container']",
      "[class*='interaction-container']",
      "[class*='note-container']"
    ]) {
      roots.push(...Array.from(document.querySelectorAll(selector)));
    }
    roots.push(document);
    return uniqueElements(roots);
  })();

  const firstText = (selectors) => {
    for (const root of detailRoots) {
      for (const selector of selectors) {
        const nodes = Array.from(root.querySelectorAll(selector));
        for (const node of nodes) {
          const text = visibleText(node);
          if (text) return text;
        }
      }
    }
    return "";
  };

  const meta = {};
  for (const m of Array.from(document.querySelectorAll("meta"))) {
    const key = m.getAttribute("property") || m.getAttribute("name");
    const content = m.getAttribute("content");
    if (key && content) meta[key] = clean(content);
  }

  const dom = {
    title: firstText([
      "#detail-title",
      ".note-content > .title",
      ".note-content .title",
      ".content > .title",
      "h1"
    ]),
    content: firstText([
      "#detail-desc .note-text",
      "#detail-desc",
      ".note-content .desc",
      ".note-content [class*='desc']",
      "[class*='note-text']",
      "[class*='desc']"
    ]),
    author_name: firstText([
      ".author-container .name",
      ".author-wrapper .name",
      ".author .name",
      "[class*='author'] [class*='name']",
      "[class*='user'] [class*='name']",
      "a[href*='/user/profile/']"
    ]),
    post_time: firstText([
      ".bottom-container .date",
      ".note-content .date",
      ".date",
      "[class*='date']",
      "[class*='time']",
      "[class*='publish']"
    ]),
    raw_liked_count: firstText([
      "[class*='like'] [class*='count']",
      "[class*='liked'] [class*='count']",
      "[class*='interact'] [class*='like']"
    ]),
    raw_collected_count: firstText([
      "[class*='collect'] [class*='count']",
      "[class*='collected'] [class*='count']",
      "[class*='interact'] [class*='collect']"
    ]),
    raw_comment_count: firstText([
      ".comments-el .total",
      ".comments-container .total",
      "[class*='comment'] [class*='count']",
      "[class*='comments'] [class*='count']",
      "[class*='interact'] [class*='comment']"
    ]),
    meta_title: meta["og:title"] || meta["twitter:title"] || document.title || "",
    meta_description: meta["description"] || meta["og:description"] || "",
  };

  const keyAliases = {
    note_id: ["noteId", "note_id", "id"],
    title: ["title", "displayTitle", "display_title", "noteTitle"],
    content: ["desc", "description", "content", "noteContent", "note_content"],
    author_name: ["nickname", "nickName", "userName", "user_name", "name"],
    post_time: ["time", "timestamp", "createTime", "create_time", "publishTime", "publish_time"],
    ip_location: ["ipLocation", "ip_location", "ip", "location"],
    raw_liked_count: ["likedCount", "liked_count", "likeCount", "like_count", "likes"],
    raw_collected_count: ["collectedCount", "collected_count", "collectCount", "collect_count", "collects"],
    raw_comment_count: ["commentCount", "comment_count", "comments"],
  };

  const readByAliases = (obj, aliases) => {
    for (const key of aliases) {
      if (Object.prototype.hasOwnProperty.call(obj, key)) {
        const value = obj[key];
        if (typeof value === "string" || typeof value === "number") return value;
      }
    }
    return "";
  };

  const readNested = (obj, paths) => {
    for (const path of paths) {
      let cur = obj;
      let ok = true;
      for (const part of path) {
        if (!cur || typeof cur !== "object" || !(part in cur)) {
          ok = false;
          break;
        }
        cur = cur[part];
      }
      if (ok && (typeof cur === "string" || typeof cur === "number")) return cur;
    }
    return "";
  };

  const noteLike = (obj) => {
    const fields = {};
    for (const [field, aliases] of Object.entries(keyAliases)) {
      const value = readByAliases(obj, aliases);
      if (value !== "") fields[field] = value;
    }

    const nestedValues = {
      author_name: readNested(obj, [
        ["user", "nickname"], ["user", "nickName"], ["user", "name"],
        ["author", "nickname"], ["author", "name"],
      ]),
      raw_liked_count: readNested(obj, [
        ["interactInfo", "likedCount"], ["interact_info", "liked_count"],
        ["interactInfo", "likeCount"],
      ]),
      raw_collected_count: readNested(obj, [
        ["interactInfo", "collectedCount"], ["interact_info", "collected_count"],
        ["interactInfo", "collectCount"],
      ]),
      raw_comment_count: readNested(obj, [
        ["interactInfo", "commentCount"], ["interact_info", "comment_count"],
      ]),
    };
    for (const [key, value] of Object.entries(nestedValues)) {
      if (value !== "" && !fields[key]) fields[key] = value;
    }

    let score = 0;
    for (const key of ["title", "content", "author_name", "post_time", "raw_liked_count", "raw_collected_count", "raw_comment_count"]) {
      if (fields[key] !== undefined && fields[key] !== "") score += 1;
    }
    if (fields.note_id && noteId && String(fields.note_id).includes(String(noteId))) score += 5;
    if (fields.content && (fields.raw_liked_count || fields.raw_comment_count || fields.author_name)) score += 2;
    return { score, fields };
  };

  const roots = [];
  for (const key of ["__INITIAL_STATE__", "__INITIAL_DATA__", "__NEXT_DATA__", "__NUXT__", "__APOLLO_STATE__"]) {
    if (window[key]) roots.push({ name: key, value: window[key] });
  }

  const candidates = [];
  const seen = new WeakSet();
  let visited = 0;

  const walk = (value, depth) => {
    if (!value || typeof value !== "object" || depth > 9 || visited > 20000) return;
    if (seen.has(value)) return;
    seen.add(value);
    visited += 1;

    if (!Array.isArray(value)) {
      const candidate = noteLike(value);
      if (candidate.score >= 3) candidates.push(candidate);
    }

    if (Array.isArray(value)) {
      for (const item of value.slice(0, 300)) walk(item, depth + 1);
    } else {
      for (const key of Object.keys(value).slice(0, 300)) walk(value[key], depth + 1);
    }
  };

  for (const root of roots) walk(root.value, 0);

  candidates.sort((a, b) => b.score - a.score);
  return {
    dom,
    state_candidates: candidates.slice(0, 8).map((item) => item.fields),
    url: location.href,
  };
}
"""
