'use strict';
(() => {
  // ---------------------------------------------------------------- 状态
  const S = {
    cata: null,
    profile: null,
    state: null,
    tab: 'avatar',
    avatarId: null,
    search: '',
    filterPath: '',
    filterElement: '',
    enhancedMode: false,   // 行迹页显示加强形态（仅 10 个加强角色可用）
    dirty: false,
    idx: {},
    conn: null,   // 已连接的私服：{ url, provider, endpoint }
    traceTree: null,     // 当前行迹树数据（节点 + 布局）
    traceEditing: null,  // 正在编辑的行迹节点
    battleMode: 'moC',   // 战斗配置：当前玩法
    battlePeriod: 0,     // 战斗配置：当前期数
    battleFloor: null,   // 战斗配置：当前层索引（null = 默认最高层）
  };
  const $ = (id) => document.getElementById(id);
  const PART_ORDER = ['HEAD', 'HAND', 'BODY', 'FOOT'];
  const PART_NAME = { HEAD: '头部', HAND: '手部', BODY: '躯干', FOOT: '脚部' };
  const PROP_NAME = {
    HPDelta: '生命值', HPRatio: '生命值%', AttackDelta: '攻击力', AttackRatio: '攻击力%',
    DefenceDelta: '防御力', DefenceRatio: '防御力%', Speed: '速度',
    CriticalChance: '暴击率', CriticalDamage: '暴击伤害',
    StatusProbability: '效果命中', StatusResistance: '效果抵抗',
    HealRatio: '治疗量加成', HPAddedRatio: '生命值%', AttackAddedRatio: '攻击力%',
    DefenceAddedRatio: '防御力%', AllDamageTypeAddedRatio: '属性伤害提高',
    PhysicalAddedRatio: '物理属性伤害提高', FireAddedRatio: '火属性伤害提高',
    IceAddedRatio: '冰属性伤害提高', ThunderAddedRatio: '雷属性伤害提高',
    WindAddedRatio: '风属性伤害提高', QuantumAddedRatio: '量子属性伤害提高',
    ImaginaryAddedRatio: '虚数属性伤害提高', BreakDamageAddedRatio: '击破特攻',
    SPRatio: '能量恢复效率',
  };
  // 客户端 AvatarPath 枚举 → 中文命途
  // Warrior=毁灭(流萤/克拉拉)、Rogue=巡猎(丹恒/希儿)、Mage=智识(景元)、
  // Warlock=虚无(佩拉)、Knight=存护(三月七/杰帕德)、Shaman=同谐(布洛妮娅)、
  // Priest=丰饶(娜塔莎)、Memory=记忆、Elation=欢愉
  const PATH_NAME = {
    Warrior: '毁灭', Rogue: '巡猎', Mage: '智识', Warlock: '虚无',
    Knight: '存护', Shaman: '同谐', Priest: '丰饶', Memory: '记忆',
    Elation: '欢愉',
  };
  const ELEMENT_NAME = {
    Physical: '物理', Fire: '火', Ice: '冰', Thunder: '雷',
    Wind: '风', Quantum: '量子', Imaginary: '虚数',
  };

  const propName = (p) => PROP_NAME[p] || p || '';
  const pathName = (p) => PATH_NAME[p] || p || '';
  const elementName = (e) => ELEMENT_NAME[e] || e || '—';

  // ---------------------------------------------------------------- API
  async function api(path, opts) {
    const resp = await fetch(path, opts);
    const text = await resp.text();
    let data;
    try { data = JSON.parse(text); } catch { data = { ok: false, message: text }; }
    if (!resp.ok && data.ok !== false) data = { ok: false, message: `HTTP ${resp.status}` };
    return data;
  }
  const postJson = (path, body) => api(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  // ---------------------------------------------------------------- toast
  let toastTimer = null;
  function toast(msg, kind = 'ok', stay = 4000) {
    const el = $('toast');
    el.textContent = msg;
    el.className = `toast ${kind}`;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, stay);
  }

  function markDirty() {
    S.dirty = true;
    $('dirty').hidden = false;
  }
  function clearDirty() {
    S.dirty = false;
    $('dirty').hidden = true;
  }

  // ---------------------------------------------------------------- 索引
  function buildIndex() {
    const c = S.cata;
    S.idx.avatar = new Map(c.avatars.map((a) => [a.id, a]));
    S.idx.lc = new Map(c.lightcones.map((x) => [x.id, x]));
    S.idx.relic = new Map(c.relics.map((x) => [x.id, x]));
    S.idx.set = new Map(c.relic_sets.map((x) => [x.id, x]));
    S.idx.main = new Map();   // group -> [affix]
    for (const a of c.relic_main_affixes) {
      if (!S.idx.main.has(a.group)) S.idx.main.set(a.group, []);
      S.idx.main.get(a.group).push(a);
    }
    S.idx.sub = new Map();
    for (const a of c.relic_sub_affixes) {
      if (!S.idx.sub.has(a.group)) S.idx.sub.set(a.group, []);
      S.idx.sub.get(a.group).push(a);
    }
    S.idx.monster = new Map(c.monsters.map((x) => [x.id, x]));
    S.idx.buff = new Map();
    for (const b of c.rogue_buffs) S.idx.buff.set(b.id, b);
  }

  const avatarCfg = (id) => S.idx.avatar.get(Number(id)) || null;
  const lcCfg = (id) => S.idx.lc.get(Number(id)) || null;
  const relicCfg = (id) => S.idx.relic.get(Number(id)) || null;
  const setName = (id) => (S.idx.set.get(Number(id)) || {}).name || `套装 ${id}`;

  // ---------------------------------------------------------------- 数据生成
  let uidSeq = 0;
  function nextUid() {
    let max = uidSeq;
    for (const lc of S.profile.lightcones || []) max = Math.max(max, Number(lc.internal_uid) || 0);
    for (const r of S.profile.relics || []) max = Math.max(max, Number(r.internal_uid) || 0);
    uidSeq = max + 1;
    return uidSeq;
  }

  function defaultSkills(cfg) {
    const skills = {}, anchors = {};
    for (const p of cfg.skill_points || []) {
      skills[String(p.point_id)] = p.max_level;
      anchors[String(p.anchor)] = p.max_level;
    }
    return { skills, anchors };
  }

  function makeAvatar(id) {
    const cfg = avatarCfg(id);
    const { skills, anchors } = defaultSkills(cfg);
    return {
      owner_uid: 0,
      avatar_id: id,
      data: { rank: cfg.max_rank, skills, skills_by_anchor_type: anchors },
      level: 80,
      promotion: cfg.max_promotion,
      techniques: [],
      sp_value: 60,
      sp_max: 120,
    };
  }

  function ensureAvatar(id) {
    const key = String(id);
    if (!S.profile.avatars[key]) {
      S.profile.avatars[key] = makeAvatar(id);
      markDirty();
    }
    return S.profile.avatars[key];
  }

  function lightconeOf(avatarId) {
    return (S.profile.lightcones || []).find((x) => Number(x.equip_avatar) === Number(avatarId)) || null;
  }

  function ensureLightcone(avatarId) {
    if (lightconeOf(avatarId)) return;
    const av = avatarCfg(avatarId);
    let pick = (S.profile.lightcones || []).length ? null : null;
    // 同命途、五星优先、id 最大（新光锥）
    const samePath = S.cata.lightcones
      .filter((x) => !av || x.path === av.path)
      .sort((a, b) => (b.rarity - a.rarity) || (b.id - a.id));
    pick = samePath[0] || S.cata.lightcones[0];
    S.profile.lightcones.push({
      level: 80, item_id: pick.id, rank: Math.min(5, pick.max_rank || 5),
      promotion: pick.max_promotion || 6, internal_uid: nextUid(), equip_avatar: Number(avatarId),
    });
    markDirty();
  }

  function relicsOf(avatarId) {
    return (S.profile.relics || []).filter((x) => Number(x.equip_avatar) === Number(avatarId));
  }

  /** 遗器部位以 4.6.53 数据目录的 Type（HEAD/HAND/BODY/FOOT）为准，别用编号尾数推断。 */
  function relicPart(relic) {
    const cfg = relicCfg(relic.relic_id);
    return cfg ? cfg.type : null;
  }

  function defaultSubAffixes(relic) {
    const group = (S.idx.sub.get(relic.sub_group) || []).filter((a) => a.affix_id > 0);
    const out = [];
    const used = new Set();
    for (const a of group) {
      if (used.has(a.property) || out.length >= 4) continue;
      used.add(a.property);
      out.push({ sub_affix_id: a.affix_id, count: 2, step: 2 });
    }
    return out;
  }

  function makeRelic(relic, avatarId) {
    const mains = (S.idx.main.get(relic.main_group) || []);
    const main = mains.find((a) => a.affix_id !== 0) || mains[0] || { affix_id: 0 };
    return {
      level: relic.max_level || 15,
      relic_id: relic.id,
      relic_set_id: relic.set_id,
      main_affix_id: main.affix_id,
      sub_affixes: defaultSubAffixes(relic),
      internal_uid: nextUid(),
      equip_avatar: Number(avatarId),
    };
  }

  /** 给角色补齐 4 个部位：选一个该部位齐全的套装。 */
  function autoRelics(avatarId) {
    const bySet = new Map();
    for (const r of S.cata.relics) {
      if (!bySet.has(r.set_id)) bySet.set(r.set_id, {});
      bySet.get(r.set_id)[r.type] = r;
    }
    let best = null, bestScore = -1;
    for (const [, parts] of bySet) {
      if (!PART_ORDER.every((p) => parts[p])) continue;
      const score = (parts.HEAD.rarity || 0) * 10 + (parts.HEAD.max_level || 0);
      if (score > bestScore) { best = parts; bestScore = score; }
    }
    if (!best) return;
    for (const part of PART_ORDER) {
      const relic = best[part];
      if (!relic) continue;
      if (relicsOf(avatarId).some((x) => relicPart(x) === part)) continue;
      S.profile.relics.push(makeRelic(relic, avatarId));
    }
    markDirty();
  }

  // ---------------------------------------------------------------- 渲染
  function renderMeta() {
    const c = S.state.catalog, p = S.state.profile;
    $('meta').textContent =
      `数据目录 ${c.version}（${c.avatars} 角色 / ${c.lightcones} 光锥 / ${c.relics} 遗器） · ` +
      `存档 ${p.exists ? `${p.avatars} 角色 / ${p.lightcones} 光锥 / ${p.relics} 遗器` : '不存在（将新建）'}`;
  }

  function renderAvatarList() {
    const box = $('avatar-list');
    const q = S.search.trim().toLowerCase();
    const rows = [];
    for (const [key, item] of Object.entries(S.profile.avatars || {})) {
      const cfg = avatarCfg(item.avatar_id || key);
      const name = cfg ? cfg.name : `角色 ${key}`;
      if (q && !name.toLowerCase().includes(q) && !String(key).includes(q)) continue;
      if (S.filterPath && (!cfg || cfg.path !== S.filterPath)) continue;
      if (S.filterElement && (!cfg || cfg.damage !== S.filterElement)) continue;
      rows.push({
        id: Number(item.avatar_id || key),
        name,
        level: item.level,
        rank: item.data?.rank,
        rarity: cfg ? Number(cfg.rarity) || 4 : 4,
      });
    }
    // 排序：8000 之后的编号沉底 → 五星在前、四星在后 → 编号从大到小
    rows.sort((a, b) => {
      const aLate = a.id >= 8000 ? 1 : 0;
      const bLate = b.id >= 8000 ? 1 : 0;
      if (aLate !== bLate) return aLate - bLate;
      if (a.rarity !== b.rarity) return b.rarity - a.rarity;
      return b.id - a.id;
    });
    box.innerHTML = rows.map((r) => `
      <div class="avatar-item ${S.avatarId === r.id ? 'active' : ''}" data-id="${r.id}">
        <img class="avatar-icon" src="/avatars/${r.id}.webp" alt=""
             onerror="this.style.visibility='hidden'">
        <span class="nm">${escapeHtml(r.name)}</span>
        <span class="lv">Lv${r.level}</span>
      </div>`).join('') || '<div class="side-hint">没有匹配的角色。</div>';
    for (const el of box.querySelectorAll('.avatar-item')) {
      el.addEventListener('click', () => selectAvatar(Number(el.dataset.id)));
    }
  }

  /** 初始化命途 / 元素筛选下拉（选项来自 catalog）。 */
  function initFilters() {
    const paths = new Map();
    const elements = new Map();
    for (const a of S.cata.avatars) {
      if (a.path) paths.set(a.path, pathName(a.path));
      if (a.damage) elements.set(a.damage, elementName(a.damage));
    }
    const fill = (id, map, allLabel) => {
      const el = $(id);
      el.innerHTML = `<option value="">${allLabel}</option>` +
        [...map.entries()].sort((x, y) => x[1].localeCompare(y[1], 'zh'))
          .map(([k, v]) => `<option value="${k}">${v}</option>`).join('');
    };
    fill('filter-path', paths, '全部命途');
    fill('filter-element', elements, '全部元素');
  }

  function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[c]);
  }

  function selectAvatar(id) {
    S.avatarId = Number(id);
    S.enhancedMode = false;   // 切换角色时回到普通形态
    ensureAvatar(S.avatarId);
    renderAvatarList();
    renderAvatarEditor();
    const content = document.querySelector('.content');
    if (content) content.scrollTop = 0;
  }

  function renderAvatarEditor() {
    const id = S.avatarId;
    $('avatar-empty').hidden = !!id;
    $('avatar-editor').hidden = !id;
    if (!id) return;
    const cfg = avatarCfg(id);
    const item = ensureAvatar(id);

    $('av-name').textContent = cfg ? cfg.name : `角色 ${id}`;
    $('av-tags').innerHTML = cfg
      ? `<span class="badge rarity${cfg.rarity}">${'★'.repeat(cfg.rarity)}</span>
         <span class="badge">${pathName(cfg.path)}</span>
         <span class="badge">${elementName(cfg.damage)}</span>
         <span class="badge">ID ${id}</span>`
      : `ID ${id}（不在 4.6.53 数据目录）`;

    $('av-level').value = item.level ?? 80;
    $('av-promotion').value = item.promotion ?? 6;
    $('av-rank').value = item.data?.rank ?? 6;
    $('av-sp-value').value = item.sp_value ?? 60;
    $('av-sp-max').value = item.sp_max ?? 120;
    $('av-techniques').value = (item.techniques || []).join(',');

    renderExRanks(cfg, item);
    renderTraces(cfg, item);
    renderLightconeEditor(cfg, item);
    renderRelicsEditor(item);
    updateProfileInfo();
  }

  /** 特殊星魂（EX）：4.6.53 只有景元(1204)/丹恒·饮月(1213)/黄泉(1308) 各一个。
   *  数据写到 item.data.ex_rank_id_list，服务端通过 AvatarPathData /
   *  BattleAvatar 的 IGDEHGIKFJA 列表下发给客户端。 */
  function renderExRanks(cfg, item) {
    const title = $('ex-rank-title');
    const box = $('ex-rank-box');
    const ex = (S.cata.ex_ranks || {})[String(item.avatar_id)] || [];
    if (!ex.length) {
      title.hidden = true;
      box.hidden = true;
      return;
    }
    title.hidden = false;
    box.hidden = false;
    const list = item.data.ex_rank_id_list || (item.data.ex_rank_id_list = []);
    box.innerHTML = ex.map((id) => `
      <label class="ex-rank">
        <input type="checkbox" value="${id}" ${list.includes(id) ? 'checked' : ''}>
        <span class="ex-name">星魂 ${id}</span>
        <span class="ex-tag">独立于 6 星魂</span>
      </label>`).join('');
    for (const input of box.querySelectorAll('input[type=checkbox]')) {
      input.addEventListener('change', () => {
        const rid = Number(input.value);
        const cur = item.data.ex_rank_id_list || (item.data.ex_rank_id_list = []);
        const idx = cur.indexOf(rid);
        if (input.checked && idx < 0) cur.push(rid);
        else if (!input.checked && idx >= 0) cur.splice(idx, 1);
        if (!cur.length) delete item.data.ex_rank_id_list;
        markDirty();
      });
    }
  }

  /** 属性加成中文名（行迹节点悬停/编辑面板用）。 */
  const STAT_NAME = {
    HPDelta: '生命值', HPRatio: '生命值%', HPAddedRatio: '生命值%',
    AttackDelta: '攻击力', AttackAddedRatio: '攻击力%',
    DefenceDelta: '防御力', DefenceAddedRatio: '防御力%',
    SpeedDelta: '速度', CriticalChanceBase: '暴击率', CriticalDamageBase: '暴击伤害',
    StatusProbabilityBase: '效果命中', StatusResistanceBase: '效果抵抗',
    BreakDamageAddedRatioBase: '击破特攻', HealRatioBase: '治疗量加成',
    SPRatioBase: '能量恢复效率', PhysicalAddedRatio: '物理伤害提高',
    FireAddedRatio: '火伤害提高', IceAddedRatio: '冰伤害提高',
    ThunderAddedRatio: '雷伤害提高', WindAddedRatio: '风伤害提高',
    QuantumAddedRatio: '量子伤害提高', ImaginaryAddedRatio: '虚数伤害提高',
    ElationDamageAddedRatioBase: '欢愉伤害提高',
  };
  function statText(type, value) {
    const name = STAT_NAME[type] || type || '';
    const num = Number(value) || 0;
    if (String(type || '').includes('Ratio') || String(type || '').includes('Chance')) {
      return `${name} +${(num * 100).toFixed(1)}%`;
    }
    return `${name} +${Number.isInteger(num) ? num : num.toFixed(1)}`;
  }

  /** 行迹：优先渲染游戏风格行迹树（网站布局 + 图标），无树数据时退回数字网格。 */
  function renderTraces(cfg, item) {
    const grid = $('trace-grid');
    const wrap = $('trace-tree-wrap');
    const box = $('trace-nodes');
    const enhWrap = $('trace-enhanced-wrap');
    const toggle = $('trace-enhanced');
    const treeData = S.cata.trace_trees?.avatars?.[String(item.avatar_id)];
    const layout = S.cata.trace_trees?.layout?.[cfg?.path];

    if (!cfg || !(cfg.skill_points || []).length) {
      grid.innerHTML = '<div class="side-hint">该角色在 4.6.53 客户端技能树表里没有行迹数据（联动/活动角色常见）。</div>';
      grid.hidden = false;
      wrap.hidden = true;
      $('trace-hint').textContent = '';
      enhWrap.hidden = true;
      return;
    }
    // 加强角色（10 个）有两套行迹：普通 18 点 + 加强 18 点
    const hasEnhanced = cfg.skill_points.some((p) => p.enhanced);
    if (!hasEnhanced) S.enhancedMode = false;
    enhWrap.hidden = !hasEnhanced;
    toggle.checked = S.enhancedMode;
    const skills = item.data.skills || (item.data.skills = {});
    const anchors = item.data.skills_by_anchor_type || (item.data.skills_by_anchor_type = {});
    const mode = S.enhancedMode ? 'tree_enhanced' : 'tree';
    const nodes = treeData?.[mode];

    if (nodes && layout) {
      // —— 游戏风格行迹树 ——
      $('trace-editor').hidden = true;
      S.traceEditing = null;
      grid.hidden = true;
      wrap.hidden = false;
      S.traceTree = { nodes, layout };
      const list = Object.entries(nodes).sort((a, b) => Number(a[0]) - Number(b[0]));
      box.innerHTML = list.map(([pid, node]) => {
        const pos = layout[node.anchor] || {};
        const style = Object.entries(pos.style || {}).map(([k, v]) => `${k}:${v}`).join(';');
        const big = String(pos.class || '').includes('main-trace');
        const lv = Number(skills[pid] ?? 0);
        const anchorNum = Number(String(node.anchor || '').replace(/\D/g, '')) || 0;
        const sp = (cfg.skill_points || []).find((x) =>
          Number(x.anchor) === anchorNum && !!x.enhanced === !!S.enhancedMode);
        let label = `锚点 ${node.anchor}`;
        if (sp && sp.name_text) {
          // 锚点 6-8 是额外能力（point_type=3），显示成「额外能力 (名字)」
          label = Number(sp.point_type) === 3
            ? `额外能力 (${sp.name_text})`
            : sp.name_text;
        }
        return `<div class="trace-node ${big ? 'big' : 'small'}" data-point="${pid}" data-anchor="${node.anchor}"
             data-max="${node.max}" data-name="${escapeHtml(label)}" style="${style}" title="${escapeHtml(label)}">
          <img src="/trace-icons/${node.icon}" alt="">
          <span class="tlv">${lv}/${node.max}</span>
        </div>`;
      }).join('');
      $('trace-hint').textContent = `${list.length} 个行迹点` +
        (hasEnhanced ? (S.enhancedMode ? '（加强形态）' : '（普通形态）') : '');
      for (const el of box.querySelectorAll('.trace-node')) {
        el.addEventListener('click', () => openTraceEditor(el));
      }
      // 连线画在命途底图 traces/<Path>.svg 里
      $('trace-tree').style.backgroundImage = `url(/traces/${cfg.path || 'Knight'}.svg)`;
      return;
    }

    // —— 无树数据：退回数字网格 ——
    wrap.hidden = true;
    grid.hidden = false;
    const points = cfg.skill_points.filter((p) => !!p.enhanced === S.enhancedMode);
    $('trace-hint').textContent = `${points.length} 个行迹点` +
      (hasEnhanced ? (S.enhancedMode ? '（加强形态）' : '（普通形态）') : '');
    grid.innerHTML = points.map((p) => {
      const val = Number(skills[String(p.point_id)] ?? 0);
      const label = p.anchor ? `锚点 ${p.anchor}` : '行迹';
      return `<label class="trace" title="PointID ${p.point_id}">
        <span class="tname">${label}</span>
        <input type="number" min="0" max="${p.max_level}" value="${val}"
               data-point="${p.point_id}" data-anchor="${p.anchor}" data-max="${p.max_level}">
        <span class="max">/${p.max_level}</span>
      </label>`;
    }).join('');
    for (const input of grid.querySelectorAll('input')) {
      input.addEventListener('input', () => {
        const point = input.dataset.point;
        const anchor = input.dataset.anchor;
        const max = Number(input.dataset.max) || 1;
        const val = Math.max(0, Math.min(max, Number(input.value) || 0));
        skills[point] = val;
        if (!S.enhancedMode && anchor && Number(anchor) > 0) anchors[anchor] = val;
        markDirty();
      });
      input.addEventListener('change', () => {
        const max = Number(input.dataset.max) || 1;
        input.value = Math.max(0, Math.min(max, Number(input.value) || 0));
      });
    }
  }

  /** 点开行迹节点编辑器（等级 +/-、满级、属性加成）。 */
  function openTraceEditor(el) {
    const pid = el.dataset.point;
    const node = S.traceTree?.nodes?.[pid];
    if (!node) return;
    const max = Number(node.max) || 1;
    const item = ensureAvatar(S.avatarId);
    const skills = item.data.skills || (item.data.skills = {});
    S.traceEditing = { pid, node, el };
    $('te-title').textContent = el.dataset.name || `锚点 ${node.anchor || ''}`;
    $('te-max').textContent = `/${max}`;
    $('te-level').max = max;
    $('te-level').value = Number(skills[pid] ?? 0);
    $('te-adds').innerHTML = (node.adds || []).map((a) =>
      `<span>${statText(a.type, a.value)}</span>`).join('');
    const ed = $('trace-editor');
    const wrapEl = $('trace-tree-wrap');
    ed.hidden = false;
    const left = Math.min(el.offsetLeft + el.offsetWidth + 12, wrapEl.clientWidth - 240);
    const top = Math.min(el.offsetTop, Math.max(8, wrapEl.clientHeight - 200));
    ed.style.left = `${Math.max(8, left)}px`;
    ed.style.top = `${top}px`;
  }

  /** 设置当前编辑节点的等级（同步 skills / 锚点表 / 节点文本）。 */
  function setTraceLevel(val) {
    const st = S.traceEditing;
    if (!st) return;
    const max = Number(st.node.max) || 1;
    const v = Math.max(0, Math.min(max, Number(val) || 0));
    const item = ensureAvatar(S.avatarId);
    const skills = item.data.skills || (item.data.skills = {});
    const anchors = item.data.skills_by_anchor_type || (item.data.skills_by_anchor_type = {});
    skills[st.pid] = v;
    const anchor = Number(String(st.node.anchor || '').replace(/\D/g, '')) || 0;
    if (!S.enhancedMode && anchor > 0) anchors[anchor] = v;
    const lv = st.el.querySelector('.tlv');
    if (lv) lv.textContent = `${v}/${max}`;
    $('te-level').value = v;
    markDirty();
  }

  function renderLightconeEditor(cfg, item) {
    const select = $('lc-select');
    const cur = lightconeOf(item.avatar_id);
    const groups = new Map();
    for (const lc of S.cata.lightcones) {
      const g = pathName(lc.path);
      if (!groups.has(g)) groups.set(g, []);
      groups.get(g).push(lc);
    }
    let html = '<option value="0">（无光锥）</option>';
    for (const [g, list] of [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0], 'zh'))) {
      html += `<optgroup label="${escapeHtml(g)}">`;
      for (const lc of list.sort((a, b) => (b.rarity - a.rarity) || (b.id - a.id))) {
        html += `<option value="${lc.id}" ${cur && Number(cur.item_id) === lc.id ? 'selected' : ''}>` +
          `${'★'.repeat(lc.rarity)} ${escapeHtml(lc.name)} (#${lc.id})</option>`;
      }
      html += '</optgroup>';
    }
    select.innerHTML = html;
    $('lc-level').value = cur ? cur.level : 80;
    $('lc-rank').value = cur ? cur.rank : 1;
    $('lc-promotion').value = cur ? (cur.promotion ?? 6) : 6;
    const disabled = !cur;
    for (const id of ['lc-level', 'lc-rank', 'lc-promotion']) $(id).disabled = disabled;
  }

  function renderRelicsEditor(item) {
    const box = $('relic-grid');
    const cur = relicsOf(item.avatar_id);
    const byPart = {};
    for (const r of cur) {
      const part = relicPart(r);
      if (part && !byPart[part]) byPart[part] = r;
    }
    box.innerHTML = PART_ORDER.map((part) => {
      const relic = byPart[part] || null;
      const cfg = relic ? relicCfg(relic.relic_id) : null;
      return `<div class="relic-card" data-part="${part}">
        <div class="rc-head"><b>${PART_NAME[part]}</b>
          <span class="hint">${cfg ? `#${cfg.id}` : '未装备'}</span></div>
        <div class="rc-body">
          <select class="relic-pick" data-part="${part}">${relicOptions(cfg ? cfg.id : 0, part)}</select>
          ${relic ? relicBody(relic, cfg) : '<div class="sub-label">选择一件遗器即可编辑主副词条</div>'}
        </div>
      </div>`;
    }).join('');

    for (const sel of box.querySelectorAll('.relic-pick')) {
      sel.addEventListener('change', () => {
        const part = sel.dataset.part;
        const rid = Number(sel.value);
        const list = S.profile.relics;
        const idx = list.findIndex((r) => Number(r.equip_avatar) === Number(item.avatar_id) &&
          relicPart(r) === part);
        if (!rid) {
          if (idx >= 0) list.splice(idx, 1);
        } else {
          const chosen = relicCfg(rid);
          if (idx >= 0) list.splice(idx, 1, makeRelic(chosen, item.avatar_id));
          else list.push(makeRelic(chosen, item.avatar_id));
        }
        markDirty();
        renderRelicsEditor(item);
      });
    }
    for (const el of box.querySelectorAll('[data-relic-field]')) {
      // select 不触发 input 事件，主词条/等级这类控件要用 change
      el.addEventListener('change', () => {
        const part = el.closest('.relic-card').dataset.part;
        const relic = byPart[part];
        if (!relic) return;
        const field = el.dataset.relicField;
        relic[field] = Number(el.value) || 0;
        markDirty();
      });
    }
    for (const sel of box.querySelectorAll('[data-sub-select]')) {
      sel.addEventListener('change', () => {
        const part = sel.closest('.relic-card').dataset.part;
        const relic = byPart[part];
        if (!relic) return;
        const i = Number(sel.dataset.subIndex);
        relic.sub_affixes[i].sub_affix_id = Number(sel.value) || 0;
        markDirty();
      });
    }
    for (const inp of box.querySelectorAll('[data-sub-field]')) {
      inp.addEventListener('input', () => {
        const part = inp.closest('.relic-card').dataset.part;
        const relic = byPart[part];
        if (!relic) return;
        const i = Number(inp.dataset.subIndex);
        const field = inp.dataset.subField;
        const v = Number(inp.value) || 0;
        relic.sub_affixes[i][field] = Math.max(0, Math.min(field === 'count' ? 5 : 9, v));
        markDirty();
      });
    }
  }

  function relicOptions(selected, part) {
    const groups = new Map();
    for (const r of S.cata.relics) {
      if (part && r.type !== part) continue;
      const g = setName(r.set_id);
      if (!groups.has(g)) groups.set(g, []);
      groups.get(g).push(r);
    }
    let html = '<option value="0">（空）</option>';
    for (const [g, list] of [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0], 'zh'))) {
      html += `<optgroup label="${escapeHtml(g)}">`;
      for (const r of list.sort((a, b) => (b.rarity - a.rarity) || (b.id - a.id))) {
        html += `<option value="${r.id}" ${r.id === selected ? 'selected' : ''}>` +
          `${'★'.repeat(r.rarity)} ${escapeHtml(g)} · ${PART_NAME[r.type] || r.type} (#${r.id})</option>`;
      }
      html += '</optgroup>';
    }
    return html;
  }

  function relicBody(relic, cfg) {
    if (!cfg) return '<div class="sub-label">该遗器不在 4.6.53 数据目录</div>';
    const mains = (S.idx.main.get(cfg.main_group) || []);
    const mainOpts = mains.map((a) => `<option value="${a.affix_id}" ${
      Number(a.affix_id) === Number(relic.main_affix_id) ? 'selected' : ''}>` +
      `${propName(a.property)} (${a.property})</option>`).join('');
    const subs = (S.idx.sub.get(cfg.sub_group) || []).filter((a) => a.affix_id > 0);
    const subOpts = (sel) => subs.map((a) => `<option value="${a.affix_id}" ${
      Number(a.affix_id) === Number(sel) ? 'selected' : ''}>${propName(a.property)}</option>`).join('');
    const rows = (relic.sub_affixes || []).slice(0, 4).map((sub, i) => `
      <div class="affix-row">
        <select data-sub-select data-sub-index="${i}">${subOpts(sub.sub_affix_id)}</select>
        <input type="number" min="0" max="5" value="${sub.count}" data-sub-field="count"
               data-sub-index="${i}" title="档位">
        <input type="number" min="0" max="9" value="${sub.step}" data-sub-field="step"
               data-sub-index="${i}" title="强化次数">
      </div>`).join('');
    return `
      <label class="field">等级
        <input type="number" min="0" max="${cfg.max_level}" value="${relic.level}"
               data-relic-field="level">
      </label>
      <label class="field">主词条
        <select data-relic-field="main_affix_id">${mainOpts || '<option value="0">—</option>'}</select>
      </label>
      <div class="sub-label">副词条（SELECT / 档位 / 强化次数）</div>
      ${rows}`;
  }

  // ---------------------------------------------------------------- 战斗配置
  // ---------------------------------------------------------------- 战斗配置
  /** 战斗配置页：旧版手动编辑（回合/关卡/波次/祝福）+ Enemy Picker 预置选择。 */
  function renderBattle() {
    renderBattlePicker();
  }

  function renderBattleConfig() {
    const bc = S.profile.battle_config || (S.profile.battle_config = {});
    $('bc-cycles').value = bc.cycle_count ?? 30;
    $('bc-stage').value = bc.stage_id ?? 0;
    $('bc-type').value = bc.battle_type ?? 'DEFAULT';

    const waves = bc.monsters || (bc.monsters = []);
    $('wave-list').innerHTML = waves.map((wave, wi) => `
      <div class="wave" data-wave="${wi}">
        <div class="wave-head"><b>第 ${wi + 1} 波</b>
          <button class="ghost mini" data-wave-add-row>＋ 怪物</button>
          <button class="ghost mini danger" data-wave-del>删除本波</button>
        </div>
        ${wave.map((m, mi) => `
          <div class="monster-row" data-monster="${mi}">
            <select data-mfield="monster_id">${monsterOptions(m.monster_id)}</select>
            <input type="number" min="1" max="200" value="${m.level ?? 80}" data-mfield="level" title="等级">
            <input type="number" min="1" max="20" value="${m.amount ?? 1}" data-mfield="amount" title="数量">
            <button class="ghost mini danger" data-mdel>删</button>
          </div>`).join('')}
      </div>`).join('') || '<div class="side-hint">还没有波次。点「＋一波」开始。</div>';

    $('wave-list').oninput = (ev) => {
      const row = ev.target.closest('.monster-row');
      if (!row) return;
      const wave = waves[Number(row.closest('.wave').dataset.wave)];
      const m = wave[Number(row.dataset.monster)];
      const field = ev.target.dataset.mfield;
      m[field] = Number(ev.target.value) || 0;
      markDirty();
    };
    $('wave-list').onclick = (ev) => {
      const t = ev.target;
      if (t.matches('[data-wave-add-row]')) {
        const wi = Number(t.closest('.wave').dataset.wave);
        waves[wi].push({ monster_id: S.cata.monsters[0]?.id || 0, level: 80, amount: 1 });
      } else if (t.matches('[data-wave-del]')) {
        waves.splice(Number(t.closest('.wave').dataset.wave), 1);
      } else if (t.matches('[data-mdel]')) {
        const wave = waves[Number(t.closest('.wave').dataset.wave)];
        wave.splice(Number(t.closest('.monster-row').dataset.monster), 1);
      } else { return; }
      markDirty();
      renderBattle();
    };

    const buffs = bc.blessings || (bc.blessings = []);
    $('buff-list').innerHTML = buffs.map((b, i) => `
      <div class="buff-row" data-buff="${i}">
        <select data-bfield="id">${buffOptions(b.id)}</select>
        <input type="number" min="1" max="99" value="${b.level ?? 1}" data-bfield="level">
        <button class="ghost mini danger" data-bdel>删</button>
      </div>`).join('') || '<div class="side-hint">没有祝福。</div>';
    $('buff-list').oninput = (ev) => {
      const row = ev.target.closest('.buff-row');
      if (!row) return;
      const b = buffs[Number(row.dataset.buff)];
      const f = ev.target.dataset.bfield;
      b[f] = Number(ev.target.value) || 0;
      markDirty();
    };
    $('buff-list').onclick = (ev) => {
      if (!ev.target.matches('[data-bdel]')) return;
      buffs.splice(Number(ev.target.closest('.buff-row').dataset.buff), 1);
      markDirty();
      renderBattle();
    };

    $('bc-cycles').oninput = () => { bc.cycle_count = Number($('bc-cycles').value) || 1; markDirty(); };
    $('bc-stage').oninput = () => { bc.stage_id = Number($('bc-stage').value) || 0; markDirty(); };
    $('bc-type').oninput = () => { bc.battle_type = $('bc-type').value; markDirty(); };
  }


  // ---------------------------------------------------------------- 战斗配置（Enemy Picker）
  function monsterName(id) {
    const m = (S.cata.monsters || []).find((x) => Number(x.id) === Number(id));
    return m ? `${m.name} (${id})` : `怪物 ${id}`;
  }

  /** 战斗配置页：4 玩法（混沌/虚构/末日/异相仲裁）+ 自定义怪。 */
  function renderBattle() {
    renderBattlePicker();
  }

  function renderBattlePicker() {
    const presets = S.cata.battle_presets || {};
    const mode = S.battleMode || 'moC';
    for (const t of document.querySelectorAll('.ep-tab')) {
      t.classList.toggle('active', t.dataset.mode === mode);
    }
    const custom = mode === 'custom';
    $('ep-side-row').hidden = custom || mode === 'anomalyArbitration';
    $('ep-turbulence-row').hidden = mode !== 'moC';   // 湍流是混沌专有
    $('ep-custom-row').hidden = !custom;
    $('ep-period').disabled = custom;
    $('ep-floor').disabled = custom;
    const periods = ((presets[mode] || {}).periods) || [];
    const psel = $('ep-period');
    psel.innerHTML = periods.map((p) =>
      `<option value="${p.period}">第 ${p.period} 期${p.name ? ` · ${p.name}` : ''}</option>`).join('')
      || '<option value="">（没有数据）</option>';
    if (S.battlePeriod && periods.some((p) => p.period === S.battlePeriod)) {
      psel.value = S.battlePeriod;
    } else {
      S.battlePeriod = periods.length ? periods[periods.length - 1].period : 0;
      psel.value = S.battlePeriod;
    }
    renderBattleFloor();
    renderBattleCurrent();
  }

  /** 层数下拉：跟期数走。 */
  function renderBattleFloor() {
    const mode = S.battleMode || 'moC';
    const preset = (S.cata.battle_presets || {})[mode];
    const fsel = $('ep-floor');
    if (mode === 'custom' || !preset) { fsel.innerHTML = '<option value="">-</option>'; return; }
    const per = preset.periods.find((p) => p.period === Number($('ep-period').value));
    const floors = (per && per.floors) || [];
    fsel.innerHTML = floors.map((f, i) => {
      const tag = mode === 'anomalyArbitration' ? `第 ${f.floor} 关` : `第 ${f.floor} 层`;
      return `<option value="${i}">${tag}${f.name ? ` · ${f.name}` : ''}</option>`;
    }).join('') || '<option value="">-</option>';
    if (S.battleFloor !== null && S.battleFloor < floors.length) {
      fsel.value = S.battleFloor;
    } else {
      S.battleFloor = Math.max(0, floors.length - 1);   // 默认最高层
      fsel.value = S.battleFloor;
    }
    renderBattleSide();
  }

  /** 当前层：有星启时 Side 才出现「第三节点」。 */
  function renderBattleSide() {
    const f = currentFloor();
    const tierce = (f && f.tierce) || [];
    const opt = $('ep-side-tierce');
    opt.hidden = !tierce.length;
    const sel = $('ep-side');
    if (!tierce.length && sel.value === '3') sel.value = '1';
    renderBattleMonsters();
  }

  /** 当前选中的层对象。 */
  function currentFloor() {
    const mode = S.battleMode || 'moC';
    const preset = (S.cata.battle_presets || {})[mode];
    if (!preset) return null;
    const per = preset.periods.find((p) => p.period === Number($('ep-period').value));
    if (!per) return null;
    return per.floors[Number($('ep-floor').value)] || null;
  }

  /** 当前挑战（期/层/节点）的怪物波次。 */
  function renderBattleMonsters() {
    const mode = S.battleMode || 'moC';
    const box = $('ep-monsters');
    if (mode === 'custom') {
      box.innerHTML = '<div class="side-hint">输入怪物 ID（逗号分隔），点「应用为战斗配置」作为一波。</div>';
      return;
    }
    const f = currentFloor();
    if (!f) { box.innerHTML = '<div class="side-hint">没有挑战数据。</div>'; return; }
    const side = $('ep-side').value;
    let waves;
    if (mode === 'anomalyArbitration') waves = f.waves || [];
    else if (side === '3') waves = f.tierce || [];
    else if (side === '2') waves = f.bot || [];
    else waves = f.top || [];
    const curInvForMark = (mode === 'anomalyArbitration'
      ? f.invasion
      : (side === '3' ? f.invasion_tierce : side === '2' ? f.invasion_bot : f.invasion_top));
    const pollutedIds = new Set((curInvForMark && curInvForMark.monsters) || []);
    const wavesHtml = (waves || []).map((wave, wi) =>
      `<div class="ep-wave-line"><b>第 ${wi + 1} 波</b>` +
      wave.filter((x) => x > 0)
        .map((id) => pollutedIds.has(id)
          ? `<span class="ep-chip ep-chip-polluted">${escapeHtml(monsterName(id))}（污染）</span>`
          : `<span class="ep-chip">${escapeHtml(monsterName(id))}</span>`).join('') +
      '</div>').join('');
    const groups = [];
    const group = (title, body) =>
      `<div class="ep-group"><span class="ep-tierce">${title}</span><span class="ep-chips">${body}</span></div>`;
    if ((f.tag_buffs || []).length) {
      groups.push(group('敌人词条：',
        f.tag_buffs.map((b) => `<span class="ep-chip ep-chip-tierce">${escapeHtml(b.name || ('#' + b.id))}</span>`).join('')));
    }
    if (mode === 'moC' && (f.buff_infos || []).length) {
      groups.push(group('关卡 Buff：',
        f.buff_infos.map((b) =>
          `<span class="ep-chip ep-chip-tierce" title="${escapeHtml(b.desc || '')}">${escapeHtml(b.name || ('#' + b.id))}</span>` +
          `<span class="ep-desc">${escapeHtml(b.desc || '')}</span>`).join('')));
    }
    let seasonList = f.season_buffs || [];
    if ((f.season_groups || []).length) {
      const sideIdx = (Number($('ep-side').value) || 1) - 1;
      seasonList = f.season_groups[sideIdx] || seasonList;
    }
    if (seasonList.length) {
      const opts = seasonList.map((b, i) =>
        `<option value="${b.id || ''}" ${i === 0 ? 'selected' : ''}>${escapeHtml(b.name)}</option>`).join('');
      groups.push(group('赛季效果（三选一）：',
        `<select id="ep-season">${opts}</select>` +
        `<span class="ep-desc" id="ep-season-desc">${escapeHtml(seasonList[0].desc || '')}</span>`));
    }
    if ((f.stage_buffs || []).length) {
      groups.push(group('关卡 Buff：',
        f.stage_buffs.map((b) =>
          `<span class="ep-chip ep-chip-tierce">${escapeHtml(b.name || ('#' + b.id))}</span>` +
          `<span class="ep-desc">${escapeHtml(b.desc || '')}</span>`).join('')));
    }
    if ((f.options || []).length) {
      groups.push(group('可选 Buff：',
        f.options.map((o) =>
          `<span class="ep-chip ep-chip-tierce" title="${escapeHtml(o.desc || '')}">${escapeHtml(o.name)}</span>`).join('')));
    }
    const curInv = mode === 'anomalyArbitration'
      ? f.invasion
      : (side === '3' ? f.invasion_tierce : side === '2' ? f.invasion_bot : f.invasion_top);
    const showInvasion = !!curInv;
    if (showInvasion) {
      groups.push(group(`贪饕污染 Lv.${curInv.level}`,
        '<span class="ep-desc">该节点的部分怪物被污染（波次里已标注「污染」）。</span>'));
    }
    const body = `<div class="ep-waves">${wavesHtml}</div>` + groups.join('');
    box.innerHTML = body || '<div class="side-hint">这一层没有怪物数据。</div>';
    const seasonSel = $('ep-season');
    if (seasonSel) {
      const descOf = (id) => {
        const b = (seasonList.find((x) => String(x.id) === String(id)) || seasonList[0] || {});
        return b.desc || '';
      };
      seasonSel.addEventListener('change', () => {
        const el = $('ep-season-desc');
        if (el) el.textContent = descOf(seasonSel.value);
      });
    }
  }

  /** 显示当前 battle_config（波次 / 祝福 / 回合）。 */
  function renderBattleCurrent() {
    const bc = S.profile.battle_config || {};
    const waves = bc.monsters || [];
    const box = $('ep-current');
    if (!waves.length && !(bc.blessings || []).length) {
      box.innerHTML = '<div class="side-hint">当前战斗配置为空。</div>';
      return;
    }
    const rows = waves.map((wave, wi) => {
      const names = (wave || []).map((m) => {
        const cnt = Number(m.amount) > 1 ? ` ×${m.amount}` : '';
        return escapeHtml(monsterName(m.monster_id)) + cnt;
      }).join('、');
      return `<div class="ep-wave"><b>第 ${wi + 1} 波</b>${names || '（空）'}</div>`;
    }).join('');
    const bl = (bc.blessings || []).map((b) => b.id).join(', ') || '无';
    box.innerHTML = `<div class="ep-current-title">当前战斗配置</div>${rows}
      <div class="ep-wave">祝福: ${bl} · 回合数: ${bc.cycle_count ?? 30}</div>
      <button id="ep-clear" class="ghost mini danger">清空战斗配置</button>`;
    const btn = $('ep-clear');
    if (btn) btn.addEventListener('click', () => {
      S.profile.battle_config = {};
      markDirty();
      renderBattle();
    });
  }

  /** 把当前选择应用为战斗配置（一波怪物 + 可选祝福）。 */
  function applyBattlePick() {
    const mode = S.battleMode || 'moC';
    const bc = S.profile.battle_config || (S.profile.battle_config = {});
    const cycle = $('ep-cycle').checked;
    const turbulence = $('ep-turbulence').checked;
    const waves = [];
    const toWave = (ids) => ids.filter((x) => x > 0)
      .map((id) => ({ monster_id: id, amount: 1, level: 80 }));
    if (mode === 'custom') {
      const ids = ($('ep-custom-ids').value || '').split(/[\s,，]+/).filter(Boolean).map(Number);
      if (!ids.length) { toast('请输入怪物 ID', 'warn'); return; }
      waves.push(toWave(ids));
    } else {
      const f = currentFloor();
      if (!f) { toast('没有可用的挑战数据', 'warn'); return; }
      const side = $('ep-side').value;
      let base;
      if (mode === 'anomalyArbitration') base = f.waves || [];
      else if (side === '3') base = f.tierce || [];
      else if (side === '2') base = f.bot || [];
      else base = f.top || [];
      for (const w of base) waves.push(toWave(w));
      // 污染（invasion）按节点独立
      const curInv = (mode === 'anomalyArbitration'
        ? f.invasion
        : (side === '3' ? f.invasion_tierce : side === '2' ? f.invasion_bot : f.invasion_top));
      const useInvasion = !!curInv;
      if (useInvasion && (curInv.monsters || []).length) {
        // 虚构/混沌的污染怪本来就在波次里（只标记）；末日/异相仲裁的「额外污染目标」不在波次，并入第 1 波
        const inWaves = new Set(waves.reduce((acc, w) => acc.concat(w.map((m) => m.monster_id)), []));
        const extra = (curInv.monsters || []).filter((id) => id && !inWaves.has(id));
        if (extra.length) {
          const extraWave = toWave(extra);
          if (waves.length) waves[0].push(...extraWave);
          else waves.push(extraWave);
        }
      }
      // create_battle 也按 stage_id 加载战斗配置：必须写对应节点的关卡 stage_id（stage=0 会卡加载）
      bc.stage_id = mode === 'anomalyArbitration'
        ? (f.stage || 0)
        : (side === '3' ? (f.stage_tierce || 0)
          : side === '2' ? (f.stage_bot || 0) : (f.stage_top || 0));
      {
        const bl = [];
        for (const b of f.tag_buffs || []) bl.push({ id: b.id, level: 1 });
        for (const id of f.buff_ids || []) bl.push({ id, level: 1 });
        if (useInvasion && curInv.buff) bl.push({ id: curInv.buff, level: 1 });
        if (f.turbulence) bl.push({ id: f.turbulence, level: 1 });
        const seasonSel = $('ep-season');
        if (seasonSel && seasonSel.value) bl.push({ id: Number(seasonSel.value), level: 1 });
        bc.blessings = bl;
      }
      if (cycle && f.cycle) bc.cycle_count = f.cycle;
    }
    bc.monsters = waves.filter((w) => w.length);
    if (cycle) bc.cycle_count = bc.cycle_count || 30;
    markDirty();
    toast(`已应用 ${bc.monsters.reduce((n, w) => n + w.length, 0)} 个怪物、stage_id=${bc.stage_id || 0}`, 'ok');
    renderBattle();
  }

  function monsterOptions(selected) {
    const sorted = [...S.cata.monsters].sort((a, b) => (a.name || '').localeCompare(b.name || '', 'zh'));
    let html = '';
    for (const m of sorted) {
      html += `<option value="${m.id}" ${m.id === Number(selected) ? 'selected' : ''}>` +
        `${escapeHtml(m.name || '?')} (#${m.id})</option>`;
    }
    return html;
  }

  function buffOptions(selected) {
    const known = S.idx.buff.get(Number(selected));
    let html = '';
    if (selected && !known) {
      html += `<option value="${selected}" selected>#${selected}（旧数据/自定义）</option>`;
    }
    const seen = new Set();
    for (const b of S.cata.rogue_buffs) {
      if (seen.has(b.id)) continue;
      seen.add(b.id);
      html += `<option value="${b.id}" ${b.id === Number(selected) ? 'selected' : ''}>` +
        `#${b.id} · ${b.category} · ${b.type}</option>`;
    }
    return html;
  }

  // ---------------------------------------------------------------- 工具
  function renderTools() {
    $('profile-info').textContent = JSON.stringify({
      path: S.state.profile.path,
      exists: S.state.profile.exists,
      mtime: S.state.profile.mtime,
      catalog: S.state.catalog,
      counts: {
        avatars: Object.keys(S.profile.avatars || {}).length,
        lightcones: (S.profile.lightcones || []).length,
        relics: (S.profile.relics || []).length,
      },
    }, null, 2);
  }

  function updateProfileInfo() { renderTools(); }

  // ---------------------------------------------------------------- 事件
  function bindEvents() {
    for (const tab of document.querySelectorAll('.tab')) {
      tab.addEventListener('click', () => {
        S.tab = tab.dataset.tab;
        for (const t of document.querySelectorAll('.tab')) t.classList.toggle('active', t === tab);
        for (const p of document.querySelectorAll('.pane')) {
          p.classList.toggle('active', p.id === `pane-${S.tab}`);
        }
        for (const v of document.querySelectorAll('.view')) {
          v.hidden = v.id !== `view-${S.tab === 'help' ? 'avatar' : S.tab}`;
        }
        if (S.tab === 'battle') renderBattle();
        if (S.tab === 'tools') renderTools();
        if (S.tab === 'help') $('view-avatar').hidden = true;
      });
    }
    for (const t of document.querySelectorAll('.ep-tab')) {
      t.addEventListener('click', () => {
        S.battleMode = t.dataset.mode;
        S.battlePeriod = 0;
        S.battleFloor = null;
        renderBattle();
      });
    }
    $('ep-period').addEventListener('change', () => {
      S.battlePeriod = Number($('ep-period').value) || 0;
      S.battleFloor = null;
      renderBattleFloor();
    });
    $('ep-floor').addEventListener('change', () => {
      S.battleFloor = Number($('ep-floor').value) || 0;
      renderBattleSide();
    });
    $('ep-side').addEventListener('change', () => renderBattleMonsters());
    $('ep-apply').addEventListener('click', applyBattlePick);

    $('search').addEventListener('input', () => { S.search = $('search').value; renderAvatarList(); });
    $('filter-path').addEventListener('change', () => {
      S.filterPath = $('filter-path').value;
      renderAvatarList();
    });
    $('filter-element').addEventListener('change', () => {
      S.filterElement = $('filter-element').value;
      renderAvatarList();
    });

    const bindAvatarField = (id, fn) => $(id).addEventListener('input', () => {
      const item = ensureAvatar(S.avatarId);
      fn(item);
      markDirty();
      renderAvatarList();
    });
    bindAvatarField('av-level', (item) => {
      item.level = clamp(Number($('av-level').value) || 1, 1, 80);
    });
    bindAvatarField('av-promotion', (item) => {
      item.promotion = clamp(Number($('av-promotion').value) || 0, 0, 6);
    });
    bindAvatarField('av-rank', (item) => {
      item.data.rank = clamp(Number($('av-rank').value) || 0, 0, 6);
    });
    bindAvatarField('av-sp-value', (item) => {
      item.sp_value = Math.max(0, Number($('av-sp-value').value) || 0);
    });
    bindAvatarField('av-sp-max', (item) => {
      item.sp_max = Math.max(0, Number($('av-sp-max').value) || 0);
    });
    bindAvatarField('av-techniques', (item) => {
      item.techniques = $('av-techniques').value.split(',').map((x) => Number(x.trim()))
        .filter((x) => x > 0);
    });

    $('trace-enhanced').addEventListener('change', () => {
      S.enhancedMode = $('trace-enhanced').checked;
      renderTraces(avatarCfg(S.avatarId), ensureAvatar(S.avatarId));
    });
    // 点击弹窗 / 行迹节点以外的区域关闭节点编辑器
    document.addEventListener('click', (ev) => {
      const ed = $('trace-editor');
      if (!ed || ed.hidden) return;
      if (ed.contains(ev.target)) return;
      if (ev.target.closest && ev.target.closest('.trace-node')) return;
      ed.hidden = true;
      S.traceEditing = null;
    });
    $('te-minus').addEventListener('click', () => {
      setTraceLevel((Number($('te-level').value) || 0) - 1);
    });
    $('te-plus').addEventListener('click', () => {
      setTraceLevel((Number($('te-level').value) || 0) + 1);
    });
    $('te-level').addEventListener('change', () => setTraceLevel($('te-level').value));
    $('te-close').addEventListener('click', () => {
      $('trace-editor').hidden = true;
      S.traceEditing = null;
    });
    $('btn-trace-max').addEventListener('click', () => {
      const cfg = avatarCfg(S.avatarId);
      const item = ensureAvatar(S.avatarId);
      const points = (cfg?.skill_points || []).filter((p) => !!p.enhanced === S.enhancedMode);
      for (const p of points) {
        item.data.skills[String(p.point_id)] = p.max_level;
        // 普通形态才写锚点表（服务端 create_skill_tree 用；加强点不覆盖普通锚点）
        if (!S.enhancedMode && p.anchor) {
          item.data.skills_by_anchor_type[String(p.anchor)] = p.max_level;
        }
      }
      markDirty();
      renderAvatarEditor();
    });
    $('lc-select').addEventListener('change', () => {
      const item = ensureAvatar(S.avatarId);
      const rid = Number($('lc-select').value);
      const cur = lightconeOf(S.avatarId);
      S.profile.lightcones = (S.profile.lightcones || [])
        .filter((x) => Number(x.equip_avatar) !== Number(S.avatarId));
      if (rid) {
        const cfg = lcCfg(rid);
        S.profile.lightcones.push({
          level: cur ? cur.level : 80,
          item_id: rid,
          rank: cur ? cur.rank : Math.min(5, cfg?.max_rank || 5),
          promotion: cfg?.max_promotion ?? 6,
          internal_uid: cur ? cur.internal_uid : nextUid(),
          equip_avatar: Number(S.avatarId),
        });
      }
      markDirty();
      renderLightconeEditor(avatarCfg(S.avatarId), item);
      renderRelicsEditor(item);
    });
    for (const [sel, field] of [['lc-level', 'level'], ['lc-rank', 'rank'], ['lc-promotion', 'promotion']]) {
      $(sel).addEventListener('input', () => {
        const cur = lightconeOf(S.avatarId);
        if (!cur) return;
        cur[field] = Number($(sel).value) || 0;
        markDirty();
      });
    }
    $('btn-lc-clear').addEventListener('click', () => {
      S.profile.lightcones = (S.profile.lightcones || [])
        .filter((x) => Number(x.equip_avatar) !== Number(S.avatarId));
      markDirty();
      renderAvatarEditor();
    });
    $('btn-relic-auto').addEventListener('click', () => {
      autoRelics(S.avatarId);
      renderRelicsEditor(ensureAvatar(S.avatarId));
    });

    $('btn-bulk-max').addEventListener('click', () => {
      for (const [key, item] of Object.entries(S.profile.avatars || {})) {
        const cfg = avatarCfg(item.avatar_id || key);
        if (cfg) {
          item.level = 80;
          item.promotion = cfg.max_promotion;
          item.data.rank = cfg.max_rank;
          for (const p of cfg.skill_points || []) {
            item.data.skills[String(p.point_id)] = p.max_level;
            if (p.anchor) item.data.skills_by_anchor_type[String(p.anchor)] = p.max_level;
          }
        }
      }
      markDirty();
      toast('全部角色已满级 / 满行迹 / 满星魂', 'ok');
      if (S.avatarId) renderAvatarEditor();
    });
    $('btn-bulk-lc').addEventListener('click', () => {
      let n = 0;
      for (const [key, item] of Object.entries(S.profile.avatars || {})) {
        const id = Number(item.avatar_id || key);
        if (!lightconeOf(id)) { ensureLightcone(id); n++; }
      }
      markDirty();
      toast(`已为 ${n} 个角色补光锥`, 'ok');
      if (S.avatarId) renderAvatarEditor();
    });
    $('btn-bulk-relic').addEventListener('click', () => {
      let n = 0;
      for (const [key, item] of Object.entries(S.profile.avatars || {})) {
        const id = Number(item.avatar_id || key);
        if (!relicsOf(id).length) { autoRelics(id); n++; }
      }
      markDirty();
      toast(`已为 ${n} 个角色补齐遗器`, 'ok');
      if (S.avatarId) renderAvatarEditor();
    });

    // ---------------------------------------------------------------- 上传 / 下载
    $('btn-upload').addEventListener('click', () => $('upload-file').click());
    $('upload-file').addEventListener('change', async () => {
      const file = $('upload-file').files[0];
      if (!file) return;
      try {
        const data = JSON.parse(await file.text());
        applyProfile(data);
        toast(`已上传 ${file.name}：${Object.keys(data.avatars).length} 角色 / `
              + `${data.lightcones.length} 光锥`, 'ok', 5000);
      } catch (err) {
        toast(`上传失败：${err.message}`, 'err', 7000);
      }
      $('upload-file').value = '';
    });
    $('btn-download').addEventListener('click', downloadProfile);

    // ---------------------------------------------------------------- 同步到私服
    $('btn-connect').addEventListener('click', openConnectModal);
    $('conn-close').addEventListener('click', closeConnectModal);
    $('connect-modal').addEventListener('click', (ev) => {
      if (ev.target === $('connect-modal')) closeConnectModal();
    });
    $('conn-provider').addEventListener('change', () => {
      if ($('conn-provider').value === 'SilverWolfHoney') {
        $('conn-url').value = PROVIDER_URLS.SilverWolfHoney;
      }
    });
    $('conn-submit').addEventListener('click', connectServer);
    $('conn-sync').addEventListener('click', syncServer);
    $('conn-disconnect').addEventListener('click', disconnectServer);
  }

  // 各私服类型的默认 dispatch 地址（都走 21000）
  const PROVIDER_URLS = {
    SilverWolfHoney: 'http://127.0.0.1:21000',
  };

  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

  /** 把上传的 JSON 载入为当前编辑中的存档。 */
  function applyProfile(data) {
    if (!data || typeof data !== 'object') throw new Error('不是 JSON 对象');
    if (typeof data.avatars !== 'object' || data.avatars === null
        || !Array.isArray(data.lightcones) || !Array.isArray(data.relics)) {
      throw new Error('不是 freesr-data.json 结构（需要 avatars/lightcones/relics）');
    }
    S.profile = data;
    S.avatarId = null;
    uidSeq = 0;
    renderAvatarList();
    renderAvatarEditor();
    updateProfileInfo();
    clearDirty();
  }

  /** 下载当前编辑后的存档：优先弹系统保存位置对话框，不支持则走浏览器下载。 */
  async function downloadProfile() {
    const text = JSON.stringify(S.profile, null, 2);
    const name = 'freesr-data.json';
    if (window.showSaveFilePicker) {
      try {
        const handle = await window.showSaveFilePicker({
          suggestedName: name,
          types: [{ description: 'JSON 文件', accept: { 'application/json': ['.json'] } }],
        });
        const writable = await handle.createWritable();
        await writable.write(text);
        await writable.close();
        clearDirty();
        toast(`已保存到 ${handle.name}`, 'ok', 5000);
        return;
      } catch (err) {
        if (err && err.name === 'AbortError') return;  // 用户取消了保存
        // 其他错误（如浏览器不支持）回退到普通下载
      }
    }
    const blob = new Blob([text], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
    clearDirty();
    toast('已下载 freesr-data.json', 'ok', 5000);
  }

  /** 根据是否已连接，切换弹窗的「连接」/「断开+同步」两种视图。 */
  function renderConnState() {
    const connected = !!S.conn;
    $('conn-form').hidden = connected;
    $('conn-connected').hidden = !connected;
    if (connected) $('conn-endpoint').textContent = S.conn.endpoint || S.conn.url;
    $('btn-connect').textContent = connected ? '已连接' : '同步到私服';
    $('btn-connect').title = connected
      ? `已连接 ${S.conn.endpoint || S.conn.url}`
      : '连接私服并推送当前配置';
  }

  /** 打开「同步到私服」对话框。已连接时直接显示「断开连接 / 同步」。 */
  function openConnectModal() {
    if (!S.conn) {
      let saved = {};
      try { saved = JSON.parse(localStorage.getItem('srtools-conn') || '{}'); } catch { /* ignore */ }
      $('conn-provider').value = saved.provider || 'SilverWolfHoney';
      $('conn-url').value = saved.url || PROVIDER_URLS.SilverWolfHoney;
    }
    renderConnState();
    $('connect-modal').hidden = false;
    ($('conn-form').hidden ? $('conn-sync') : $('conn-url')).focus();
  }

  function closeConnectModal() { $('connect-modal').hidden = true; }

  /** 连接私服：只验证连接（不推送数据）。 */
  async function connectServer() {
    const url = $('conn-url').value.trim();
    const provider = $('conn-provider').value;
    const btn = $('conn-submit');
    btn.disabled = true;
    btn.textContent = '连接中…';
    try {
      const res = await postJson('/api/connect', { url, provider });
      if (res.ok) {
        S.conn = { url, provider, endpoint: res.endpoint || url };
        localStorage.setItem('srtools-conn', JSON.stringify({ url, provider }));
        renderConnState();
        toast('连接成功', 'ok', 3000);
      } else {
        toast(`连接失败：${res.message || JSON.stringify(res)}`, 'err', 8000);
      }
    } catch (err) {
      toast(`请求失败：${err.message}`, 'err', 8000);
    } finally {
      btn.disabled = false;
      btn.textContent = '连接';
    }
  }

  /** 把当前编辑的配置推送给已连接的私服。 */
  async function syncServer() {
    if (!S.conn) return;
    const btn = $('conn-sync');
    btn.disabled = true;
    btn.textContent = '同步中…';
    try {
      const res = await postJson('/api/connect', {
        url: S.conn.url, provider: S.conn.provider, data: S.profile,
      });
      if (res.ok) {
        S.conn.endpoint = res.endpoint || S.conn.endpoint;
        renderConnState();
        clearDirty();
        const warns = res.warnings || [];
        toast(res.message + (warns.length ? `\n注意：\n- ${warns.join('\n- ')}` : ''),
              warns.length ? 'warn' : 'ok', 6000);
      } else {
        if (res.stage === 'auth' || res.stage === 'network') {
          S.conn = null;   // 连接已失效，回到未连接视图
          renderConnState();
        }
        toast(`同步失败：${res.message || JSON.stringify(res)}`, 'err', 8000);
      }
    } catch (err) {
      toast(`请求失败：${err.message}`, 'err', 8000);
    } finally {
      btn.disabled = false;
      btn.textContent = '同步';
    }
  }

  function disconnectServer() {
    S.conn = null;
    renderConnState();
    toast('已断开连接', 'ok', 2500);
  }

  async function refreshState() {
    S.state = await api('/api/state');
    renderMeta();
  }

  // ---------------------------------------------------------------- 启动
  async function loadAll(silent = false) {
    try {
      const [cata, profile, state] = await Promise.all([
        api('/api/catalog'), api('/api/profile'), api('/api/state'),
      ]);
      if (!cata.meta) throw new Error('catalog 加载失败：' + (cata.message || '未知错误'));
      S.cata = cata;
      S.profile = profile.data;
      S.state = state;
      buildIndex();
      initFilters();
      uidSeq = 0;
      renderMeta();
      renderAvatarList();
      const first = Object.keys(S.profile.avatars || {})[0];
      if (first) selectAvatar(Number(first));
      else renderAvatarEditor();
      clearDirty();
      if (!silent) toast(`已载入 ${S.state.catalog.version} 数据目录`, 'ok', 2500);
    } catch (err) {
      toast(`初始化失败：${err.message}`, 'err', 9000);
      $('meta').textContent = '初始化失败';
    }
  }

  window.addEventListener('beforeunload', (ev) => {
    if (S.dirty) { ev.preventDefault(); ev.returnValue = ''; }
  });

  bindEvents();
  loadAll();
})();
