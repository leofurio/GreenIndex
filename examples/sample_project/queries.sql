-- GC030: SELECT * (query non selettiva)
SELECT * FROM orders WHERE status = 'open';

-- GC031: query senza WHERE/LIMIT su tabella potenzialmente grande
SELECT id FROM events;
