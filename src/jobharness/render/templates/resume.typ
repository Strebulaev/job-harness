// ATS-safe single-column resume. Data arrives as JSON (data.json), so no user
// text is ever interpreted as Typst markup.
#let d = json("data.json")
#set document(title: d.header.full_name + " - Resume", author: d.header.full_name)
#set page(paper: "a4", margin: (x: 1.7cm, y: 1.5cm))
#set text(font: ("Libertinus Serif", "Liberation Serif", "DejaVu Serif"), size: 10pt)
#set par(leading: 0.55em, spacing: 0.7em)
#show heading.where(level: 2): it => block(above: 1em, below: 0.5em)[
  #text(size: 11pt, weight: "bold")[#upper(it.body)]
  #line(length: 100%, stroke: 0.5pt)
]

#align(center)[
  #text(size: 17pt, weight: "bold")[#d.header.full_name] \
  #d.headline \
  #d.header.email
  #if d.header.phone != none [ | #d.header.phone]
  | #d.header.location
  #for (k, v) in d.header.links [ | #v]
]

#for line in d.summary [
  #line \
]

== Experience

#for e in d.experience [
  #text(weight: "bold")[#e.title_display], #e.employer_display \
  #e.start - #(if e.end == none [Present] else [#e.end])
  #for b in e.bullets [
    - #b.text
  ]
]

#if d.earlier_experience_line != none [
  #d.earlier_experience_line
]

#for p in d.projects [
  #text(weight: "bold")[Project: #p.name]
  #for b in p.bullets [
    - #b.text
  ]
]

== Education

#for ed in d.education [
  #text(weight: "bold")[#ed.degree, #ed.field], #ed.institution (#ed.start - #(if ed.end == none [Present] else [#ed.end])) \
]
#for c in d.certifications [
  #c.name, #c.issuer (#c.date) \
]

== Skills

#d.skills_core.join(", ") \
#if d.languages.len() > 0 [
  Languages: #d.languages.map(l => l.lang + " (" + l.level + ")").join(", ")
]
