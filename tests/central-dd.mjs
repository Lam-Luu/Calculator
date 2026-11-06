import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import { test } from 'node:test';

for (const file of ['../index.html', '../dist/index.html']) {
  const html = readFileSync(new URL(file, import.meta.url), 'utf8');
  const context = vm.createContext({});
  vm.runInContext(html.match(/<script id="calculator-engine">([\s\S]*?)<\/script>/)[1] + '\nthis.engine = Calculator;', context);
  const { parse, calculate } = context.engine;
  const totals = (input, region = 'central') => {
    const parsed = parse(input, region);
    assert.equal(parsed.warnings.length, 0);
    return JSON.parse(JSON.stringify(calculate(parsed.sums, region).dd));
  };

  test(`${file}: dd và đầu/đuôi riêng có cùng tiền khi cùng giá trị`, () => {
    for (const value of [0, 0.1, 6, 10, 30]) {
      assert.deepEqual(totals(`07 đầu ${value} đuôi ${value}`), totals(`07 dd ${value}`));
    }
    assert.deepEqual(totals('07 đầu 30 đuôi 30'), { initial: 50000, payable: 42600, profit: 7400 });
  });

  test(`${file}: đầu hoặc đuôi riêng và giá trị không bằng nhau`, () => {
    for (const input of ['45 đầu 10', '45 đui 10']) {
      assert.deepEqual(totals(input), { initial: 8333, payable: 7100, profit: 1233 });
    }
    assert.deepEqual(totals('45 đầu 10 đuôi 40'), { initial: 41667, payable: 35500, profit: 6167 });
  });

  test(`${file}: tin nhắn trộn dd và đầu/đui tính đúng phần đầu đuôi`, () => {
    const input = '00-99-28-82 lô 5 dd 10 ---00-99 đầu 15 đui 10 ---66 dd 6--39-79 lô 5 --44- dd 20 --07 dd 30 ---88-51 dd 10 --72 dd 60';
    assert.deepEqual(totals(input), { initial: 335000, payable: 285420, profit: 49580 });
  });

  test(`${file}: giữ đúng hệ số đầu và đuôi miền Bắc`, () => {
    assert.deepEqual(totals('45 đầu 10 đuôi 40', 'north'), { initial: 80000, payable: 64800, profit: 15200 });
  });
}
