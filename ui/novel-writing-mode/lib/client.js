// 写作模式：右栏的「设定 / 章节 / 正文」面板。
// 数据来自只读派生产物 .novel-ledger/view.json 清单与 UTF-8 JSON 分片。
// 经 workspaceFiles Remote 校验并完整重组；兼容旧视图与逐行正文，不改账本。
window.__ModuleLoader__.load({
	id: '@local/novel-writing-mode',
	factory: (require) => {
		var module = { exports: {} };
		var exports = module.exports;
		const React = require('react');
		const h = React.createElement;
		const { useCallback, useEffect, useMemo, useState } = React;

		const KIND = 'novel-writing';
		const ID = '@local/novel-writing-mode';
		const NS = 'novelWritingMode';
		const VIEW_DIR = '.novel-ledger';
		const PAGE_LINES = 256;
		const MAX_TRANSPORT_BYTES = 128 * 1024;
		const TABS = ['settings', 'chapters', 'text'];

		const CSS = [
			'.nwm-root{display:flex;flex-direction:column;height:100%;min-height:0;background:var(--dsw-alias-bg-base);color:var(--dsw-alias-label-primary);font-size:13px;line-height:1.55}',
			'.nwm-head{flex:0 0 auto;display:flex;flex-direction:column;gap:9px;padding:12px 14px 10px;border-bottom:.5px solid var(--dsw-alias-border-l1)}',
			'.nwm-titleRow{display:flex;align-items:center;gap:8px;min-width:0}',
			'.nwm-book{font-size:15px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
			'.nwm-meta{display:flex;align-items:center;gap:6px;flex-wrap:wrap;color:var(--dsw-alias-label-secondary);font-size:11.5px}',
			'.nwm-spacer{flex:1}',
			'.nwm-tabs{display:flex;gap:2px;padding:2px;border-radius:8px;background:var(--dsw-alias-bg-layer-2)}',
			'.nwm-tab{appearance:none;border:0;background:transparent;color:var(--dsw-alias-label-secondary);font:inherit;font-size:12px;padding:4px 12px;border-radius:6px;cursor:pointer}',
			'.nwm-tab:hover{color:var(--dsw-alias-label-primary)}',
			'.nwm-tab[data-active="true"]{background:var(--dsw-alias-bg-layer-1);color:var(--dsw-alias-label-primary)}',
			'.nwm-body{flex:1;min-height:0;overflow-y:auto;padding:12px 14px 28px}',
			'.nwm-section{margin:0 0 16px}',
			'.nwm-sectionTitle{margin:0 0 6px;font-size:11px;font-weight:600;letter-spacing:.08em;color:var(--dsw-alias-label-secondary)}',
			'.nwm-card{background:var(--dsw-alias-bg-layer-1);border:.5px solid var(--dsw-alias-border-l1);border-radius:10px;padding:9px 11px}',
			'.nwm-card + .nwm-card{margin-top:8px}',
			'.nwm-row{display:flex;align-items:center;gap:8px;min-width:0;padding:6px 8px;border-radius:8px;border:.5px solid transparent}',
			'.nwm-row[data-click="true"]{cursor:pointer}',
			'.nwm-row[data-click="true"]:hover{background:var(--dsw-alias-bg-layer-1)}',
			'.nwm-row[data-current="true"]{background:var(--dsw-alias-bg-layer-2);border-color:var(--dsw-alias-border-l1)}',
			'.nwm-rowMain{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
			'.nwm-dim{color:var(--dsw-alias-label-secondary)}',
			'.nwm-small{font-size:11.5px}',
			'.nwm-para{margin:0 0 10px;color:var(--dsw-alias-label-secondary);white-space:pre-wrap;word-break:break-word}',
			'.nwm-chip{display:inline-flex;align-items:center;gap:4px;flex:0 0 auto;font-size:11px;padding:1px 7px;border-radius:999px;border:.5px solid var(--dsw-alias-border-l1);color:var(--dsw-alias-label-secondary);white-space:nowrap}',
			'.nwm-chip[data-tone="ok"]{color:var(--dsw-alias-state-success-primary);border-color:var(--dsw-alias-state-success-primary)}',
			'.nwm-chip[data-tone="warn"]{color:var(--dsw-alias-state-warn-primary);border-color:var(--dsw-alias-state-warn-primary)}',
			'.nwm-chip[data-tone="idle"]{color:var(--dsw-alias-state-idle-primary);border-color:var(--dsw-alias-state-idle-primary)}',
			'.nwm-chip[data-tone="brand"]{color:var(--dsw-alias-brand-primary);border-color:var(--dsw-alias-brand-primary)}',
			'.nwm-dl{display:grid;grid-template-columns:auto 1fr;gap:4px 10px;margin:0;font-size:12px}',
			'.nwm-dl dt{color:var(--dsw-alias-label-secondary);white-space:nowrap}',
			'.nwm-dl dd{margin:0;word-break:break-word}',
			'.nwm-btn{appearance:none;flex:0 0 auto;border:.5px solid var(--dsw-alias-border-l2);background:var(--dsw-alias-bg-layer-1);color:var(--dsw-alias-label-primary);font:inherit;font-size:12px;padding:3px 10px;border-radius:7px;cursor:pointer}',
			'.nwm-btn:hover{background:var(--dsw-alias-bg-layer-2)}',
			'.nwm-btn:disabled{opacity:.45;cursor:default}',
			'.nwm-iconBtn{appearance:none;flex:0 0 auto;border:0;background:transparent;color:var(--dsw-alias-label-secondary);padding:4px;border-radius:6px;cursor:pointer;display:inline-flex}',
			'.nwm-iconBtn:hover{background:var(--dsw-alias-bg-layer-2);color:var(--dsw-alias-label-primary)}',
			'.nwm-entry{appearance:none;border:0;background:transparent;color:inherit;font:inherit;display:inline-flex;align-items:center;gap:6px;padding:3px 8px;border-radius:7px;cursor:pointer}',
			'.nwm-entry:hover{background:var(--dsw-alias-bg-layer-2)}',
			'.nwm-readerHead{display:flex;align-items:center;gap:8px;margin:0 0 12px}',
			'.nwm-readerTitle{flex:1;min-width:0;font-size:14px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
			'.nwm-prose{max-width:40em;margin:0 auto;font-size:15px;line-height:1.95;color:var(--dsw-alias-label-primary)}',
			'.nwm-prose p{margin:0 0 .9em;text-indent:2em;word-break:break-word}',
			'.nwm-empty{padding:26px 10px;text-align:center;color:var(--dsw-alias-label-secondary);line-height:1.85}',
			'.nwm-emptyTitle{font-size:14px;font-weight:600;color:var(--dsw-alias-label-primary);margin:0 0 6px}',
			'.nwm-code{display:block;margin:10px 0 0;padding:8px 10px;border-radius:8px;background:var(--dsw-alias-bg-layer-2);font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px;text-align:left;overflow-x:auto;white-space:pre;color:var(--dsw-alias-label-primary)}',
			'.nwm-outline{margin:0 0 16px;padding:9px 11px;border-radius:10px;background:var(--dsw-alias-bg-layer-1);border:.5px solid var(--dsw-alias-border-l1);color:var(--dsw-alias-label-secondary);font-size:12px;line-height:1.7}',
			'.nwm-outline summary{cursor:pointer;color:var(--dsw-alias-label-primary);font-weight:600;font-size:12px}',
			'.nwm-link{appearance:none;border:0;background:transparent;color:var(--dsw-alias-brand-primary);font:inherit;font-size:11.5px;padding:0;cursor:pointer}',
			'.nwm-hooksRow{display:flex;align-items:baseline;gap:8px;padding:5px 2px;border-bottom:.5px solid var(--dsw-alias-border-l1)}',
			'.nwm-hooksRow:last-child{border-bottom:0}',
		].join('\n');

		const ZH = {
			'type.title': '写作模式',
			'entry.label': '写作模式',
			'entry.aria': '打开写作模式面板',
			'guide.title': '写作模式',
			'guide.description': '阅读设定、章节信息与正文',
			'tab.settings': '设定',
			'tab.chapters': '章节',
			'tab.text': '正文',
			'loading': '正在读取写作视图…',
			'refresh': '刷新',
			'retry': '重试',
			'empty.title': '还没有写作视图',
			'empty.body': '写作视图由 novel-ledger-lite 从账本导出；在小说项目目录执行导出命令后点「刷新」。',
			'empty.hint': '已尝试读取：',
			'empty.pathLabel': '视图路径',
			'error.read': '读取失败',
			'section.premise': '核心设定',
			'section.protagonist': '主角',
			'section.style': '文风',
			'section.rules': '规则与要点',
			'section.characters': '人物',
			'section.world': '世界',
			'section.hooks': '伏笔',
			'section.resources': '资源',
			'section.places': '地点',
			'section.progress': '进度',
			'field.name': '姓名',
			'field.identity': '身份',
			'field.desire': '欲望',
			'field.limit': '限制',
			'field.role': '角色',
			'field.place': '所在',
			'field.clock': '故事日',
			'field.chapters': '章数',
			'field.words': '字数',
			'field.profile': '内置档',
			'field.source': '外部档案',
			'field.status': '状态',
			'status.running': '进行中',
			'status.done': '已完本',
			'chapter.written': '已写',
			'chapter.outlined': '有章纲',
			'chapter.planned': '待写',
			'hook.paid': '已兑',
			'hook.open': '未兑',
			'hook.extended': '延期',
			'hook.dropped': '放弃',
			'reader.prev': '上一章',
			'reader.next': '下一章',
			'reader.outline': '章纲与概要',
			'reader.empty': '选择一章查看正文',
			'reader.missing': '这一章还没有正文',
			'reader.han': '字',
			'chapters.none': '还没有章节',
			'vol.written': '已写',
			'hooks.due': '应在第 {n} 章兑现',
			'empty.command': 'python3 <技能目录>/scripts/export_view.py <bundle.json> --out .novel-ledger',
		};

		const EN = {
			'type.title': 'Writing Mode',
			'entry.label': 'Writing',
			'entry.aria': 'Open the writing mode panel',
			'guide.title': 'Writing Mode',
			'guide.description': "Read the setting, chapters, and prose",
			'tab.settings': 'Setting',
			'tab.chapters': 'Chapters',
			'tab.text': 'Prose',
			'loading': 'Reading the writing view…',
			'refresh': 'Refresh',
			'retry': 'Retry',
			'empty.title': 'No writing view yet',
			'empty.body': 'novel-ledger-lite exports this view from its ledger. Run the export in the novel project, then press Refresh.',
			'empty.hint': 'Tried: ',
			'empty.pathLabel': 'View path',
			'error.read': 'Read failed',
			'section.premise': 'Core setting',
			'section.protagonist': 'Protagonist',
			'section.style': 'Style',
			'section.rules': 'Rules',
			'section.characters': 'Characters',
			'section.world': 'World',
			'section.hooks': 'Hooks',
			'section.resources': 'Resources',
			'section.places': 'Places',
			'section.progress': 'Progress',
			'field.name': 'Name',
			'field.identity': 'Identity',
			'field.desire': 'Desire',
			'field.limit': 'Limit',
			'field.role': 'Role',
			'field.place': 'Place',
			'field.clock': 'Story day',
			'field.chapters': 'Chapters',
			'field.words': 'Words',
			'field.profile': 'Profile',
			'field.source': 'Source file',
			'field.status': 'Status',
			'status.running': 'Drafting',
			'status.done': 'Finished',
			'chapter.written': 'Written',
			'chapter.outlined': 'Outlined',
			'chapter.planned': 'Planned',
			'hook.paid': 'Paid',
			'hook.open': 'Open',
			'hook.extended': 'Extended',
			'hook.dropped': 'Dropped',
			'reader.prev': 'Previous',
			'reader.next': 'Next',
			'reader.outline': 'Outline and summary',
			'reader.empty': 'Pick a chapter to read',
			'reader.missing': 'This chapter has no prose yet',
			'reader.han': 'chars',
			'chapters.none': 'No chapters yet',
			'vol.written': 'written',
			'hooks.due': 'due in chapter {n}',
			'empty.command': 'python3 <skill>/scripts/export_view.py <bundle.json> --out .novel-ledger',
		};

		function dirOf(path) {
			const index = String(path).lastIndexOf('/');
			return index < 0 ? '' : String(path).slice(0, index);
		}

		function joinPath(dir, name) {
			if (!dir) return name;
			return dir.replace(/\/+$/, '') + '/' + String(name).replace(/^\/+/, '');
		}

		function errText(error) {
			if (!error) return '';
			if (typeof error === 'string') return error;
			if (typeof error.message === 'string') return error.message;
			try { return JSON.stringify(error); } catch (e) { return String(error); }
		}

		function formatHan(value) {
			if (typeof value !== 'number' || !isFinite(value) || value <= 0) return '';
			if (value >= 10000) return (value / 10000).toFixed(value >= 100000 ? 0 : 1) + ' 万字';
			return value + ' 字';
		}

		function pad4(n) {
			let text = String(n);
			while (text.length < 4) text = '0' + text;
			return text;
		}

		function chip(label, tone) {
			return h('span', { className: 'nwm-chip', 'data-tone': tone || 'plain' }, label);
		}

		function section(title, children) {
			if (!children) return null;
			return h('div', { className: 'nwm-section' },
				h('div', { className: 'nwm-sectionTitle' }, title),
				children);
		}

		function kvRows(pairs) {
			const rows = [];
			for (const pair of pairs) {
				if (!pair || pair[1] === undefined || pair[1] === null || pair[1] === '') continue;
				rows.push(h('dt', { key: 'k' + pair[0] }, pair[0]));
				rows.push(h('dd', { key: 'v' + pair[0] }, pair[1]));
			}
			return rows.length ? h('dl', { className: 'nwm-dl' }, rows) : null;
		}

		function paragraphsOf(text) {
			const lines = String(text || '').split('\n');
			if (lines.length && /^#\s/.test(lines[0])) lines.shift();
			let blocks = lines.join('\n').split(/\n\s*\n/).map((part) => part.trim()).filter(Boolean);
			if (blocks.length === 1 && blocks[0].indexOf('\n') >= 0) {
				blocks = blocks[0].split('\n').map((part) => part.trim()).filter(Boolean);
			}
			return blocks;
		}

		function chapterLabel(entry) {
			if (!entry) return '';
			const title = entry.title || '';
			if (title.indexOf('第') === 0) return title;
			return title ? '第' + entry.n + '章 ' + title : '第' + entry.n + '章';
		}

		function statusTone(state) {
			if (state === 'written' || state === 'paid') return 'ok';
			if (state === 'outlined') return 'brand';
			return 'idle';
		}

		function guideIcon() {
			return h('svg', { width: 18, height: 18, viewBox: '0 0 32 32', fill: 'none', 'aria-hidden': 'true' },
				h('path', { d: 'M5 7.5c3.6-1.4 7.1-1.4 11 0v17c-3.9-1.4-7.4-1.4-11 0z', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round' }),
				h('path', { d: 'M27 7.5c-3.6-1.4-7.1-1.4-11 0v17c3.9-1.4 7.4-1.4 11 0z', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round' }));
		}

		// Kept independent of React so the exact transport used by the panel can be
		// exercised against a line/byte-limited workspace reader.
		function createWorkspaceReader(workspaceFiles) {
			const encoder = new TextEncoder();
			const hex = /^[0-9a-f]{64}$/;

			function fail(code, message) {
				const error = new Error(message);
				error.code = code;
				throw error;
			}

			function flag(page, names) {
				for (const source of [page, page && page.page, page && page.pagination]) {
					for (const name of names) {
						if (source && typeof source[name] === 'boolean') return source[name];
					}
				}
				return undefined;
			}

			async function page(sessionId, path, offset, limit, signal) {
				const result = await workspaceFiles.read(sessionId, path, { offset, limit }, signal);
				if (!result || result.ok !== true) {
					const error = result && result.error;
					fail((error && error.code) || 'view/read', errText(error) || '读取失败');
				}
				if (!result.value || typeof result.value.text !== 'string') fail('view/read', '读取结果缺少正文文本。');
				return result.value;
			}

			async function single(sessionId, path, signal, onFound) {
				const value = await page(sessionId, path, 1, 2, signal);
				if (onFound) onFound();
				if (flag(value, ['truncated', 'isTruncated', 'is_truncated']) === true
					|| flag(value, ['hasMore', 'has_more']) === true) {
					fail('view/incomplete', '写作视图文件读取不完整，请重新导出后刷新。');
				}
				return value.text;
			}

			async function sha256(text) {
				if (!globalThis.crypto || !globalThis.crypto.subtle) {
					fail('view/crypto', '当前界面环境不支持 SHA-256 完整性校验，无法安全读取写作视图。');
				}
				const hash = await globalThis.crypto.subtle.digest('SHA-256', encoder.encode(text));
				return Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, '0')).join('');
			}

			function parse(text) {
				try { return JSON.parse(text); }
				catch (error) { fail('view/parse', '写作视图 JSON 不完整或格式错误：' + errText(error)); }
			}

			async function content(sessionId, base, descriptor, signal) {
				if (!descriptor || descriptor.schema !== 'novel-writing-content/1'
					|| !Number.isSafeInteger(descriptor.bytes) || descriptor.bytes < 0
					|| !hex.test(descriptor.sha256 || '')
					|| !Array.isArray(descriptor.chunks) || !descriptor.chunks.length) {
					fail('view/manifest', '写作视图分片清单缺失或版本不受支持。');
				}
				const pieces = [];
				for (let index = 0; index < descriptor.chunks.length; index++) {
					const reference = descriptor.chunks[index];
					if (!reference || !hex.test(reference.sha256 || '')
						|| reference.file !== 'chunks/' + reference.sha256 + '.json'
						|| !Number.isSafeInteger(reference.bytes) || reference.bytes <= 0
						|| reference.bytes > MAX_TRANSPORT_BYTES) {
						fail('view/path', '写作视图分片路径或大小无效，拒绝读取工作区外文件。');
					}
					const text = await single(sessionId, joinPath(base, reference.file), signal);
					if (encoder.encode(text).length !== reference.bytes || await sha256(text) !== reference.sha256) {
						fail('view/integrity', '写作视图分片缺失、被截断或内容已变化，请重新导出后刷新。');
					}
					const chunk = parse(text);
					if (!chunk || chunk.schema !== 'novel-writing-chunk/1'
						|| chunk.index !== index || typeof chunk.text !== 'string') {
						fail('view/chunk', '写作视图分片版本或顺序不正确。');
					}
					pieces.push(chunk.text);
				}
				const text = pieces.join('');
				if (encoder.encode(text).length !== descriptor.bytes || await sha256(text) !== descriptor.sha256) {
					fail('view/integrity', '写作视图分片未能完整重组，请重新导出后刷新。');
				}
				return text;
			}

			async function legacyProse(sessionId, path, signal) {
				const pieces = [];
				let offset = 1;
				while (true) {
					const value = await page(sessionId, path, offset, PAGE_LINES, signal);
					const more = flag(value, ['hasMore', 'has_more']);
					if (flag(value, ['truncated', 'isTruncated', 'is_truncated']) === true
						|| encoder.encode(value.text).length >= MAX_TRANSPORT_BYTES) {
						fail('view/incomplete', '旧版正文触及读取上限，请重新导出为分片视图后阅读。');
					}
					if (!value.text) {
						if (more === true) fail('view/incomplete', '旧版正文读取不完整，请重新导出后阅读。');
						break;
					}
					const count = value.text.split('\n').length;
					if (count > PAGE_LINES || (count < PAGE_LINES && more === true)) {
						fail('view/incomplete', '旧版正文分页不完整，请重新导出为分片视图后阅读。');
					}
					pieces.push(value.text);
					if (count < PAGE_LINES || more === false) break;
					offset += count;
				}
				return pieces.join('\n');
			}

			async function safely(action) {
				try { return { ok: true, value: await action() }; }
				catch (error) { return { ok: false, error: { code: error.code || 'view/read', message: errText(error) } }; }
			}

			return {
				readView: async (sessionId, path, signal) => {
					let found = false;
					const result = await safely(async () => {
						let view = parse(await single(sessionId, path, signal, () => { found = true; }));
						if (view && view.schema === 'novel-writing-manifest/1') {
							if (view.view_schema !== 'novel-writing-view/2') fail('view/version', '写作视图版本不受支持。');
							view = parse(await content(sessionId, dirOf(path), view.content, signal));
							if (!view || view.schema !== 'novel-writing-view/2') fail('view/version', '写作视图与清单的版本不一致。');
						}
						if (!view || !['novel-writing-view/1', 'novel-writing-view/2'].includes(view.schema)
							|| !view.book || !Array.isArray(view.chapters)) {
							fail('view/version', '写作视图版本或结构不受支持，请重新导出。');
						}
						return view;
					});
					return Object.assign(result, { found });
				},
				readProse: (sessionId, path, entry, schema, signal) => safely(async () => {
					if (entry.content) return { text: await content(sessionId, dirOf(path), entry.content, signal) };
					if (schema !== 'novel-writing-view/1') fail('view/manifest', '正文分片清单缺失，请重新导出。');
					if (!/^chapters\/ch[0-9]+\.md$/.test(entry.file || '')) fail('view/path', '旧版正文文件路径无效。');
					return { text: await legacyProse(sessionId, joinPath(dirOf(path), entry.file), signal) };
				}),
			};
		}

		const INJECT = ['slots', 'locale', 'sidebarRightTabs', 'sidebarRight', 'remote', 'remote.workspaceFiles'];

		function definition(t) {
			return {
				id: ID,
				kind: KIND,
				priority: 'extension',
				title: () => t('type.title'),
				guide: [{
					id: 'writing-mode',
					order: 20,
					title: () => t('guide.title'),
					description: () => t('guide.description'),
					icon: guideIcon,
				}],
			};
		}

		function apply(ctx) {
			const t = ctx.locale.bind(NS);
			const reader = createWorkspaceReader(ctx.remote.workspaceFiles);

			async function listDirectories(sessionId, path, signal) {
				try {
					const result = await ctx.remote.workspaceFiles.list(sessionId, path, signal);
					if (!result || result.ok !== true || !result.value) return [];
					const entries = result.value.entries || [];
					const dirs = [];
					for (const entry of entries) {
						if (!entry) continue;
						const kind = entry.kind || entry.type;
						const isDir = entry.isDirectory === true || kind === 'directory' || kind === 'dir';
						if (!isDir) continue;
						const name = entry.name || (entry.absolutePath ? String(entry.absolutePath).split(/[\\/]/).pop() : '');
						if (!name || name === '.novel-ledger' || name.charAt(0) === '.') continue;
						dirs.push(name);
						if (dirs.length >= 40) break;
					}
					return dirs;
				} catch (error) {
					return [];
				}
			}

			async function locate(sessionId, signal) {
				const tried = [];
				const candidates = [joinPath(VIEW_DIR, 'view.json')];
				for (const candidate of candidates) {
					tried.push(candidate);
					const hit = await reader.readView(sessionId, candidate, signal);
					if (hit.ok === true) return { ok: true, view: hit.value, path: candidate, tried };
					if (hit.found) return Object.assign({ tried }, hit);
				}
				const dirs = await listDirectories(sessionId, '.', signal);
				for (const dir of dirs) {
					const candidate = joinPath(dir, joinPath(VIEW_DIR, 'view.json'));
					tried.push(candidate);
					const hit = await reader.readView(sessionId, candidate, signal);
					if (hit.ok === true) return { ok: true, view: hit.value, path: candidate, tried };
					if (hit.found) return Object.assign({ tried }, hit);
				}
				return { ok: false, error: { code: 'workspace-file/not-found', message: 'writing view not found' }, tried };
			}

			function openPanel() {
				try {
					const target = ctx.sidebarRight.commandTarget();
					if (target !== undefined && typeof ctx.sidebarRight.openTabFromTarget === 'function') {
						ctx.sidebarRight.openTabFromTarget(KIND, target);
						return;
					}
					ctx.sidebarRight.openTab(KIND);
				} catch (error) {
					console.error('[novel-writing-mode] open panel failed', error);
				}
			}

			// ---------------------------------------------------------------- body
			function WritingBody(props) {
				const info = typeof props.useTabInfo === 'function' ? props.useTabInfo() : {};
				const sessionId = props.sessionId;
				const tab = info.tab || {};
				const [reload, setReload] = useState(0);
				const [phase, setPhase] = useState({ kind: 'loading' });
				const [pane, setPane] = useState('settings');
				const [selected, setSelected] = useState(null);
				const [prose, setProse] = useState({ kind: 'idle' });
				const [viewPath, setViewPath] = useState(joinPath(VIEW_DIR, 'view.json'));

				const view = phase.kind === 'ready' ? phase.view : null;

				useEffect(() => {
					let alive = true;
					setPhase({ kind: 'loading' });
					locate(sessionId, tab.signal).then((hit) => {
						if (!alive) return;
						if (hit.ok === true) {
							setPhase({ kind: 'ready', view: hit.view, path: hit.path, tried: hit.tried || [] });
							setViewPath(hit.path);
						} else {
							setPhase({ kind: 'error', error: hit.error, tried: hit.tried || [] });
						}
					}).catch((error) => {
						if (!alive) return;
						setPhase({ kind: 'error', error: { message: errText(error) }, tried: [] });
					});
					return () => { alive = false; };
				}, [sessionId, reload]);

				useEffect(() => {
					if (!view) return;
					if (selected !== null) return;
					const last = view.source && typeof view.source.last_chapter === 'number' ? view.source.last_chapter : 0;
					const chapters = view.chapters || [];
					if (!chapters.length) return;
					const target = chapters.find((entry) => entry.n === last) || chapters[0];
					setSelected(target.n);
				}, [view]);

				const current = useMemo(() => {
					if (!view || selected === null) return null;
					return (view.chapters || []).find((entry) => entry.n === selected) || null;
				}, [view, selected]);

				useEffect(() => {
					if (pane !== 'text' || !current || !current.file) {
						setProse({ kind: 'idle' });
						return;
					}
					let alive = true;
					setProse({ kind: 'loading' });
					reader.readProse(sessionId, viewPath, current, view.schema, tab.signal).then((page) => {
						if (!alive) return;
						if (page.ok === true) setProse({ kind: 'ready', text: page.value.text });
						else setProse({ kind: 'error', error: page.error });
					}).catch((error) => {
						if (!alive) return;
						setProse({ kind: 'error', error: { message: errText(error) } });
					});
					return () => { alive = false; };
				}, [pane, current, viewPath, reload]);

				const chapters = view ? view.chapters || [] : [];
				const index = current ? chapters.findIndex((entry) => entry.n === current.n) : -1;
				const go = useCallback((delta) => {
					const next = chapters[index + delta];
					if (next) setSelected(next.n);
				}, [chapters, index]);

				function headerRow() {
					const book = view ? view.book || {} : {};
					const title = book.title || t('type.title');
					const written = typeof book.written === 'number' ? book.written : 0;
					const total = typeof book.chapter_count === 'number' ? book.chapter_count : 0;
					return h('div', { className: 'nwm-titleRow' },
						h('div', { className: 'nwm-book', title }, title),
						h('span', { className: 'nwm-spacer' }),
						total ? chip(written + ' / ' + total) : null,
						h('button', {
							className: 'nwm-iconBtn',
							type: 'button',
							title: t('refresh'),
							'aria-label': t('refresh'),
							onClick: () => setReload((value) => value + 1),
						}, refreshGlyph()));
				}

				function tabsRow() {
					return h('div', { className: 'nwm-tabs' }, TABS.map((key) => h('button', {
						key,
						type: 'button',
						className: 'nwm-tab',
						'data-active': String(pane === key),
						onClick: () => setPane(key),
					}, t('tab.' + key))));
				}

				function emptyState() {
					const error = phase.kind === 'error' ? phase.error : null;
					const tried = phase.kind === 'error' ? (phase.tried || []) : [];
					return h('div', { className: 'nwm-empty' },
						h('div', { className: 'nwm-emptyTitle' }, t('empty.title')),
						h('div', null, t('empty.body')),
						tried.length ? h('div', { className: 'nwm-small' }, t('empty.hint') + tried.slice(0, 4).join('、')) : null,
						error && error.message ? h('div', { className: 'nwm-small' }, t('error.read') + '：' + errText(error)) : null,
						h('code', { className: 'nwm-code' }, t('empty.command')),
						h('div', { style: { marginTop: 12 } },
							h('button', { className: 'nwm-btn', type: 'button', onClick: () => setReload((value) => value + 1) }, t('retry'))));
				}

				function settingsPane() {
					const book = view.book || {};
					const nodes = [];
					const facets = (view.facets || []).filter((facet) => facet && facet.value);
					if (facets.length) {
						nodes.push(section(t('section.premise'), h('div', { className: 'nwm-card' },
							kvRows(facets.map((facet) => [facet.label, facet.value])))));
					}
					const protagonist = view.protagonist || {};
					if (protagonist.name || protagonist.identity || protagonist.desire || protagonist.limit) {
						nodes.push(section(t('section.protagonist'), h('div', { className: 'nwm-card' },
							kvRows([
								[t('field.name'), protagonist.name],
								[t('field.identity'), protagonist.identity],
								[t('field.desire'), protagonist.desire],
								[t('field.limit'), protagonist.limit],
							]))));
					}
					const style = book.style || {};
					if (style.profile || style.source) {
						nodes.push(section(t('section.style'), h('div', { className: 'nwm-card' },
							kvRows([
								[t('field.profile'), style.profile],
								[t('field.source'), style.source],
							]))));
					}
					const rules = (view.rules || []).filter((rule) => rule && (rule.items || []).length);
					if (rules.length) {
						nodes.push(section(t('section.rules'), h('div', { className: 'nwm-card' }, rules.map((rule) => h('div', { key: rule.key, style: { marginBottom: 8 } },
							h('div', { className: 'nwm-dim nwm-small', style: { marginBottom: 4 } }, rule.title),
							(rule.items || []).map((item, position) => h('div', { key: position, className: 'nwm-para nwm-small' }, '· ' + item)))))));
					}
					const characters = view.characters || [];
					if (characters.length) {
						nodes.push(section(t('section.characters'), h('div', null, characters.map((person) => h('div', { key: person.id, className: 'nwm-card' },
							h('div', { style: { display: 'flex', alignItems: 'center', gap: 6 } },
								h('div', { style: { fontWeight: 600 } }, person.name),
								person.role ? chip(person.role) : null,
								h('span', { className: 'nwm-spacer' }),
								person.place ? h('span', { className: 'nwm-dim nwm-small' }, person.place) : null),
							(person.desire || person.limit) ? h('div', { className: 'nwm-para nwm-small', style: { marginTop: 6 } },
								[person.desire ? '欲望：' + person.desire : '', person.limit ? '限制：' + person.limit : ''].filter(Boolean).join('  ')) : null,
							(person.facts || []).length ? h('div', { style: { marginTop: 6, display: 'flex', gap: 6, flexWrap: 'wrap' } },
								person.facts.map((fact) => h('span', { key: fact.key, className: 'nwm-chip' }, fact.key + '：' + fact.value))) : null,
							(person.knowledge || []).length ? h('div', { className: 'nwm-small nwm-dim', style: { marginTop: 6 } },
								'知情：' + person.knowledge.map((row) => row.topic + '（' + row.stance + '）').join('、')) : null)))));
					}
					const worldSections = (view.world || []).filter((entry) => (entry.items || []).length);
					if (worldSections.length) {
						nodes.push(section(t('section.world'), h('div', null, worldSections.map((entry) => h('div', { key: entry.key, className: 'nwm-card' },
							h('div', { className: 'nwm-sectionTitle', style: { marginBottom: 6 } }, entry.title),
							(entry.items || []).map((item) => h('div', { key: item.id || item.title, style: { marginBottom: 8 } },
								h('div', { style: { fontWeight: 600, fontSize: 12 } }, item.title),
								kvRows((item.lines || []).map((line) => [line.label, line.value])))))))));
					}
					const hooks = (view.hooks || []);
					if (hooks.length) {
						const ordered = hooks.slice().sort((left, right) => {
							const rank = (row) => (row.status === 'paid' ? 1 : 0);
							return rank(left) - rank(right);
						});
						nodes.push(section(t('section.hooks'), h('div', { className: 'nwm-card' }, ordered.map((hook) => h('div', { key: hook.id, className: 'nwm-hooksRow' },
							chip(t('hook.' + (hook.status || 'open')), statusTone(hook.status)),
							h('div', { style: { flex: 1, minWidth: 0 } },
								h('div', { className: 'nwm-small' }, hook.text),
								typeof hook.due === 'number' ? h('div', { className: 'nwm-small nwm-dim' }, t('hooks.due').replace('{n}', String(hook.due))) : null))))));
					}
					const resources = view.resources || [];
					if (resources.length) {
						const names = {};
						for (const person of characters) names[person.id] = person.name;
						nodes.push(section(t('section.resources'), h('div', { className: 'nwm-card' }, resources.map((row, position) => h('div', { key: position, className: 'nwm-hooksRow' },
							h('div', { style: { flex: 1, minWidth: 0 } },
								h('span', { style: { fontWeight: 600 } }, names[row.holder] || row.holder),
								' · ',
								h('span', { className: 'nwm-dim' }, row.asset + (row.unit ? '（' + row.unit + '）' : ''))),
							h('div', { style: { fontWeight: 600 } }, String(row.amount)))))));
					}
					const places = view.places || [];
					if (places.length) {
						nodes.push(section(t('section.places'), h('div', { className: 'nwm-card' }, places.map((place) => h('div', { key: place.id, className: 'nwm-hooksRow' },
							h('div', { style: { flex: 1 } }, place.name),
							place.parent ? h('span', { className: 'nwm-small nwm-dim' }, place.parent) : null)))));
					}
					if (!nodes.length) return h('div', { className: 'nwm-empty' }, t('chapters.none'));
					return h('div', null, nodes);
				}

				function chapterRow(entry) {
					const isCurrent = entry.n === selected;
					return h('div', {
						key: entry.n,
						className: 'nwm-row',
						'data-click': 'true',
						'data-current': String(isCurrent),
						onClick: () => { setSelected(entry.n); setPane('text'); },
					},
						h('span', { className: 'nwm-dim nwm-small', style: { width: 28, flex: '0 0 auto', textAlign: 'right' } }, String(entry.n)),
						h('span', { className: 'nwm-rowMain' }, chapterLabel(entry) === '第' + entry.n + '章' ? (entry.synopsis || '—') : chapterLabel(entry)),
						entry.han ? h('span', { className: 'nwm-small nwm-dim' }, String(entry.han) + t('reader.han')) : null,
						chip(t('chapter.' + entry.state), statusTone(entry.state)));
				}

				function chaptersPane() {
					const volumes = view.volumes || [];
					if (!chapters.length) return h('div', { className: 'nwm-empty' }, t('chapters.none'));
					const groups = [];
					if (volumes.length) {
						volumes.forEach((volume, position) => {
							const members = chapters.filter((entry) => entry.volume === volume.id);
							if (!members.length) return;
							groups.push({ volume, members, ordinal: position + 1 });
						});
					}
					const listed = new Set(groups.map((group) => group.volume.id));
					const rest = chapters.filter((entry) => !listed.has(entry.volume));
					if (rest.length) groups.push({ volume: null, members: rest });
					return h('div', null, groups.map((group) => {
						const written = group.members.filter((entry) => entry.state === 'written').length;
						return h('div', { key: group.volume ? group.volume.id : 'rest', className: 'nwm-section' },
							group.volume ? h('div', { className: 'nwm-sectionTitle', style: { display: 'flex', gap: 6, alignItems: 'baseline' } },
								h('span', null, '第' + group.ordinal + '卷 · 第 ' + group.volume.first + '–' + group.volume.end + ' 章'),
								h('span', { className: 'nwm-dim' }, written + '/' + group.members.length),
							) : h('div', { className: 'nwm-sectionTitle' }, '其他章节'),
							group.volume && group.volume.purpose ? h('div', { className: 'nwm-para nwm-small', style: { marginBottom: 6 } }, group.volume.purpose) : null,
							group.members.map(chapterRow));
					}));
				}

				function textPane() {
					if (!current) return h('div', { className: 'nwm-empty' }, t('reader.empty'));
					const head = h('div', { className: 'nwm-readerHead' },
						h('button', { className: 'nwm-btn', type: 'button', disabled: index <= 0, onClick: () => go(-1) }, t('reader.prev')),
						h('div', { className: 'nwm-readerTitle', title: chapterLabel(current) }, chapterLabel(current)),
						current.han ? h('span', { className: 'nwm-chip' }, String(current.han) + t('reader.han')) : null,
						h('button', { className: 'nwm-btn', type: 'button', disabled: index < 0 || index >= chapters.length - 1, onClick: () => go(1) }, t('reader.next')));
					const outline = (current.synopsis || current.summary || current.beat)
						? h('details', { className: 'nwm-outline' },
							h('summary', null, t('reader.outline')),
							current.synopsis ? h('div', { style: { marginTop: 6 } }, current.synopsis) : null,
							current.summary ? h('div', { style: { marginTop: 4 } }, current.summary) : null,
							current.beat ? h('div', { style: { marginTop: 4 } }, current.beat) : null,
							(current.scenes || []).length ? h('div', { style: { marginTop: 4 } }, current.scenes.join(' / ')) : null)
						: null;
					let body = null;
					if (!current.file) {
						body = h('div', { className: 'nwm-empty' }, t('reader.missing'));
					} else if (prose.kind === 'loading' || prose.kind === 'idle') {
						body = h('div', { className: 'nwm-empty' }, t('loading'));
					} else if (prose.kind === 'error') {
						body = h('div', { className: 'nwm-empty' }, t('error.read') + '：' + errText(prose.error));
					} else {
						const parts = paragraphsOf(prose.text);
						body = h('div', { className: 'nwm-prose' }, parts.map((part, position) => h('p', { key: position }, part)));
					}
					return h('div', null, head, outline, body);
				}

				let content = null;
				if (phase.kind === 'loading') content = h('div', { className: 'nwm-empty' }, t('loading'));
				else if (phase.kind === 'error') content = emptyState();
				else content = pane === 'chapters' ? chaptersPane() : pane === 'text' ? textPane() : settingsPane();

				return h('div', { className: 'nwm-root' },
					h('style', null, CSS),
					h('div', { className: 'nwm-head' }, headerRow(), tabsRow()),
					h('div', { className: 'nwm-body' }, content));
			}

			function refreshGlyph() {
				return h('svg', { width: 14, height: 14, viewBox: '0 0 16 16', fill: 'none', 'aria-hidden': 'true' },
					h('path', { d: 'M13 8a5 5 0 1 1-1.5-3.5', stroke: 'currentColor', strokeWidth: 1.5, strokeLinecap: 'round' }),
					h('path', { d: 'M13 2.5V5h-2.5', stroke: 'currentColor', strokeWidth: 1.5, strokeLinecap: 'round', strokeLinejoin: 'round' }));
			}

			function WritingTitle() {
				return h('span', null, t('type.title'));
			}

			function HeaderEntry() {
				return h('button', {
					className: 'nwm-entry',
					type: 'button',
					title: t('entry.aria'),
					'aria-label': t('entry.aria'),
					onClick: () => openPanel(),
				},
					h('span', { style: { display: 'inline-flex', color: 'var(--dsw-alias-label-secondary)' } }, guideIcon()),
					h('span', { className: 'nwm-small' }, t('entry.label')));
			}

			ctx.effect(() => ctx.locale.register(NS, { zh: ZH, en: EN }), 'novel-writing-mode: dictionaries');
			ctx.effect(() => ctx.sidebarRightTabs.register(definition(t)), 'novel-writing-mode: tab type');
			ctx.effect(() => ctx.slots.inject('sidebar.right.pane.tab', () => ctx.slots.register({
				name: 'sidebar.right.pane.tab',
				key: ID,
				locale: NS,
			}, WritingBody)), 'novel-writing-mode: tab body');
			ctx.effect(() => ctx.slots.inject('sidebar.right.pane.tab.title', () => ctx.slots.register({
				name: 'sidebar.right.pane.tab.title',
				key: ID,
			}, WritingTitle)), 'novel-writing-mode: tab title');
			ctx.effect(() => ctx.slots.inject('conversation.session.header.utilities', () => ctx.slots.register({
				name: 'conversation.session.header.utilities',
				id: 'novel-writing-mode',
				order: 30,
				label: t('entry.label'),
			}, HeaderEntry)), 'novel-writing-mode: header entry');
		}

		exports.inject = INJECT;
		exports.createWorkspaceReader = createWorkspaceReader;
		exports.apply = apply;
		return module.exports;
	},
});
