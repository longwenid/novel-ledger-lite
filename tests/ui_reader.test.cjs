// No browser libraries or npm install: execute the actual shipped client factory.
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { webcrypto, createHash } = require('node:crypto');

const root = process.argv[2];
const entrypoint = '.novel-ledger/view.json';
const budget = 128 * 1024;
const client = fs.readFileSync(path.join(__dirname, '../ui/novel-writing-mode/lib/client.js'), 'utf8');

function loadReader(host, crypto = webcrypto) {
	let exported;
	const context = {
		TextEncoder, Uint8Array, crypto,
		window: { __ModuleLoader__: { load(definition) {
			exported = definition.factory(() => ({ createElement() {} }));
		} } },
	};
	vm.runInNewContext(client, context, { filename: 'client.js' });
	return exported.createWorkspaceReader(host);
}

function hostAt(directory) {
	const calls = [];
	const overrides = new Map();
	return {
		calls, overrides,
		async read(sessionId, name, options) {
			calls.push({ name, ...options });
			const full = path.resolve(directory, name);
			assert.ok(full.startsWith(path.resolve(directory) + path.sep));
			let text;
			try {
				if (overrides.has(name)) {
					const override = overrides.get(name);
					if (override === null) throw new Error('missing');
					text = override;
				} else text = fs.readFileSync(full, 'utf8');
			} catch (error) {
				return { ok: false, error: { code: 'workspace-file/not-found', message: name + ' missing' } };
			}
			const lines = text.split('\n');
			const selected = lines.slice(options.offset - 1, options.offset - 1 + options.limit);
			let value = selected.join('\n');
			const truncated = Buffer.byteLength(value) > budget;
			if (truncated) value = Buffer.from(value).subarray(0, budget).toString('utf8');
			return { ok: true, value: {
				text: value, truncated,
				hasMore: options.offset - 1 + selected.length < lines.length,
			} };
		},
	};
}

function newHost(name = 'long') {
	return hostAt(path.join(root, name));
}

function manifest(host, book = 'long') {
	return JSON.parse(host.overrides.get(entrypoint)
		|| fs.readFileSync(path.join(root, book, entrypoint), 'utf8'));
}

function hash(text) {
	return createHash('sha256').update(text).digest('hex');
}

test('3000-chapter UTF-8 view reassembles completely below the per-read byte ceiling', async () => {
	const host = newHost('large');
	const result = await loadReader(host).readView('session', entrypoint);
	assert.equal(result.ok, true, JSON.stringify(result.error));
	assert.equal(result.value.chapters.length, 3000);
	assert.equal(result.value.chapters[0].synopsis.length, 200);
	assert.equal(result.value.chapters[0].beat.length, 400);
	assert.equal(result.value.chapters[2999].synopsis.length, 160);
	assert.equal(result.value.chapters[2999].beat.length, 160);
	assert.equal(result.value.chapters[2999].scenes.length, 3);
	assert.ok(manifest(host, 'large').content.bytes > 2 * 1024 * 1024);
	assert.ok(host.calls.length > 2);
	assert.ok(host.calls.every(call => call.offset === 1 && call.limit === 2));
});

test('accepted 6004-line chapter renders exactly, including its ending', async () => {
	const host = newHost();
	const reader = loadReader(host);
	const view = await reader.readView('session', entrypoint);
	assert.equal(view.ok, true);
	const body = await reader.readProse('session', entrypoint, view.value.chapters[0], view.value.schema);
	assert.equal(body.ok, true, JSON.stringify(body.error));
	const expected = fs.readFileSync(path.join(root, 'long/.novel-ledger/chapters/ch0001.md'), 'utf8');
	assert.equal(expected.split('\n').length, 6005);
	assert.equal(body.value.text, expected);
});

test('legacy view/1 still reads all正文 pages', async () => {
	const host = newHost();
	host.overrides.set(entrypoint, JSON.stringify({
		schema: 'novel-writing-view/1', book: {}, chapters: [{ n: 1, file: 'chapters/ch0001.md' }],
	}));
	const reader = loadReader(host);
	const view = await reader.readView('session', entrypoint);
	assert.equal(view.ok, true);
	const result = await reader.readProse('session', entrypoint, view.value.chapters[0], view.value.schema);
	assert.equal(result.ok, true, JSON.stringify(result.error));
	assert.equal(result.value.text, fs.readFileSync(path.join(root, 'long/.novel-ledger/chapters/ch0001.md'), 'utf8'));
	assert.ok(host.calls.some(call => call.offset > 5000));
});

test('legacy byte truncation is an error, never a ready正文', async () => {
	const host = newHost();
	host.overrides.set('.novel-ledger/chapters/ch0001.md', '汉'.repeat(100000));
	const result = await loadReader(host).readProse('session', entrypoint,
		{ file: 'chapters/ch0001.md' }, 'novel-writing-view/1');
	assert.equal(result.ok, false);
	assert.equal(result.error.code, 'view/incomplete');
});

test('missing chunks retain the useful error and mark the entrypoint as found', async () => {
	const host = newHost();
	const file = '.novel-ledger/' + manifest(host).content.chunks[0].file;
	host.overrides.set(file, null);
	const result = await loadReader(host).readView('session', entrypoint);
	assert.equal(result.ok, false);
	assert.equal(result.found, true);
	assert.equal(result.error.code, 'workspace-file/not-found');
});

test('same-byte content corruption fails SHA-256 verification', async () => {
	const host = newHost();
	const file = '.novel-ledger/' + manifest(host).content.chunks[0].file;
	const raw = fs.readFileSync(path.join(root, 'long', file), 'utf8');
	host.overrides.set(file, raw.replace('夜', '日'));
	const result = await loadReader(host).readView('session', entrypoint);
	assert.equal(result.ok, false);
	assert.equal(result.error.code, 'view/integrity');
});

test('workspace traversal references are rejected before a read', async () => {
	const host = newHost();
	const data = manifest(host);
	data.content.chunks[0].file = '../secrets.json';
	host.overrides.set(entrypoint, JSON.stringify(data));
	const result = await loadReader(host).readView('session', entrypoint);
	assert.equal(result.ok, false);
	assert.equal(result.error.code, 'view/path');
	assert.equal(host.calls.length, 1);
});

test('a validly hashed unsupported chunk version is rejected', async () => {
	const host = newHost();
	const data = manifest(host);
	const reference = data.content.chunks[0];
	const file = '.novel-ledger/' + reference.file;
	const chunk = JSON.parse(fs.readFileSync(path.join(root, 'long', file), 'utf8'));
	chunk.schema = 'novel-writing-chunk/99';
	const text = JSON.stringify(chunk);
	reference.sha256 = hash(text);
	reference.file = 'chunks/' + reference.sha256 + '.json';
	reference.bytes = Buffer.byteLength(text);
	host.overrides.set('.novel-ledger/' + reference.file, text);
	host.overrides.set(entrypoint, JSON.stringify(data));
	const result = await loadReader(host).readView('session', entrypoint);
	assert.equal(result.ok, false);
	assert.equal(result.error.code, 'view/chunk');
});

test('reordered valid chunks fail sequence verification', async () => {
	const host = newHost('large');
	const data = manifest(host, 'large');
	data.content.chunks.reverse();
	host.overrides.set(entrypoint, JSON.stringify(data));
	const result = await loadReader(host).readView('session', entrypoint);
	assert.equal(result.ok, false);
	assert.equal(result.error.code, 'view/chunk');
});

test('a mismatched final content hash rejects otherwise valid chunks', async () => {
	const host = newHost();
	const data = manifest(host);
	data.content.sha256 = '0'.repeat(64);
	host.overrides.set(entrypoint, JSON.stringify(data));
	const result = await loadReader(host).readView('session', entrypoint);
	assert.equal(result.ok, false);
	assert.equal(result.error.code, 'view/integrity');
});

test('unsupported view versions are explicit errors', async () => {
	const host = newHost();
	const data = manifest(host);
	data.view_schema = 'novel-writing-view/99';
	host.overrides.set(entrypoint, JSON.stringify(data));
	const result = await loadReader(host).readView('session', entrypoint);
	assert.equal(result.ok, false);
	assert.equal(result.error.code, 'view/version');
});

test('missing WebCrypto reports an unsupported environment', async () => {
	const host = newHost();
	const result = await loadReader(host, null).readView('session', entrypoint);
	assert.equal(result.ok, false);
	assert.equal(result.error.code, 'view/crypto');
});
