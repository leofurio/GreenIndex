"""Esempio didattico: contiene volutamente diverse violazioni green."""

import time

import requests


def process(users, products):
    # GC001: ciclo annidato (complessità quadratica)
    matches = []
    for user in users:
        for product in products:
            if user["pref"] == product["category"]:
                matches.append((user, product))

    # GC002: concatenazione di stringhe in un ciclo
    report = ""
    for m in matches:
        report += str(m) + "\n"

    # GC020: chiamata di rete dentro un ciclo  +  GC022: senza timeout
    for user in users:
        requests.get("https://api.example.com/notify/" + str(user["id"]))

    return report


def load_config(path):
    # GC011: open() senza context manager  +  GC010: read() dell'intero file
    f = open(path)
    data = f.read()
    return data


def enrich(rows, db):
    # GC021: query al DB dentro un ciclo (pattern N+1)
    out = []
    for row in rows:
        record = db.query("SELECT * FROM details WHERE id = %s", row["id"])
        out.append(record)
    return out


def worker():
    # GC003: busy-wait / polling attivo
    while True:
        check_queue()
        time.sleep(1)


def check_queue():
    print("checking queue...")  # GC040: print di debug
