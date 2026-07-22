import test from 'node:test'
import assert from 'node:assert/strict'

import {
  filterHostsByOwner,
  getOwnerOptions,
  sortHosts,
} from '../src/utils/hostList.mjs'


const hosts = [
  { id: 1, hostname: 'web-2', owner: '张三' },
  { id: 2, hostname: 'web-1', owner: '李四' },
  { id: 3, hostname: 'db-1', owner: '' },
  { id: 4, hostname: 'api-1', owner: '张三' },
  { id: 5, hostname: 'cache-1' },
]

test('owner options are unique, non-empty, and sorted', () => {
  assert.deepEqual(getOwnerOptions(hosts), ['李四', '张三'])
})

test('owner filter matches the selected owner exactly', () => {
  assert.deepEqual(filterHostsByOwner(hosts, '张三').map(host => host.id), [1, 4])
  assert.equal(filterHostsByOwner(hosts, '').length, hosts.length)
})

test('host sorting supports ascending and descending owner order', () => {
  assert.deepEqual(sortHosts(hosts, 'owner', true).map(host => host.id), [3, 5, 2, 1, 4])
  assert.deepEqual(sortHosts(hosts, 'owner', false).map(host => host.id), [1, 4, 2, 3, 5])
})

test('host sorting does not mutate the source list', () => {
  const original = [...hosts]
  sortHosts(hosts, 'hostname', true)
  assert.deepEqual(hosts, original)
})
