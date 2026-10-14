//! Formateur AirLang, basé sur les tokens (pas sur des regex).
//!
//! Garanties (vérifiées par les tests) :
//!   * les tokens ne changent jamais : seuls l'indentation et l'espacement bougent ;
//!   * chaque ligne reste une ligne (les sauts de ligne sont significatifs en AirLang) ;
//!   * le formatage est idempotent : formater deux fois = formater une fois ;
//!   * les commentaires et les chaînes sont recopiés tels quels.

use crate::lexer::{lex_line, Kind, Tok};

pub const INDENT: &str = "    ";

/// Mots-clés suivis d'un espace avant `(` : `if (x)`, `not (a)`, mais `print(x)`.
const SPACED_BEFORE_PAREN: [&str; 15] = [
    "if", "while", "unless", "match", "in", "and", "or", "not", "return", "then", "else", "for",
    "catch", "const", "as",
];
/// Mots-clés après lesquels un `-` est unaire (`return -1`, `x and -y`).
const UNARY_AFTER: [&str; 12] = [
    "return", "in", "and", "or", "not", "if", "while", "unless", "match", "then", "else", "for",
];
#[derive(Clone, Copy, PartialEq)]
enum Block {
    Plain,
    Trait,
    Blueprint,
}

/// Une ligne de sortie. Les champs de blueprint gardent leurs morceaux pour être alignés ensuite.
struct Line {
    text: String,
    field: Option<Field>,
}

struct Field {
    indent: usize,
    name: String,
    rest: String,
}

/// Un `-` est unaire s'il suit un début de ligne, un opérateur, une ouverture ou un mot-clé.
fn minus_is_unary(prev: Option<&Tok>, prev_unary: bool) -> bool {
    match prev {
        None => true,
        Some(p) => {
            if prev_unary {
                return true;
            }
            match p.kind {
                Kind::Op => !matches!(p.text.as_str(), ")" | "]" | "}" | "?"),
                Kind::Word => UNARY_AFTER.contains(&p.text.as_str()),
                _ => false,
            }
        }
    }
}

fn space_between(prev: &Tok, cur: &Tok, prev_unary: bool) -> bool {
    if prev_unary {
        return false;
    }
    if matches!(prev.text.as_str(), "(" | "[" | "{" | "@" | "." | "..") && prev.kind == Kind::Op {
        return false;
    }
    if cur.kind == Kind::Op && matches!(cur.text.as_str(), ")" | "]" | "}" | "," | "." | ".." | "?" | ":") {
        return false;
    }
    if cur.kind == Kind::Op && cur.text == "(" {
        return match prev.kind {
            Kind::Word => SPACED_BEFORE_PAREN.contains(&prev.text.as_str()),
            Kind::Op => !matches!(prev.text.as_str(), ")" | "]" | "?"),
            _ => true,
        };
    }
    if cur.kind == Kind::Op && cur.text == "[" {
        return match prev.kind {
            Kind::Word => SPACED_BEFORE_PAREN.contains(&prev.text.as_str()),
            Kind::Op => !matches!(prev.text.as_str(), ")" | "]" | "?"),
            _ => false,
        };
    }
    true
}

/// Rend les tokens d'une ligne (sans indentation).
fn render(toks: &[Tok]) -> String {
    let mut out = String::new();
    let mut prev: Option<&Tok> = None;
    let mut prev_unary = false;
    for t in toks {
        if t.kind == Kind::Comment {
            if !out.is_empty() {
                out.push_str("  ");
            }
            out.push_str(&t.text);
            break;
        }
        let unary = t.is("-") && minus_is_unary(prev, prev_unary);
        if let Some(p) = prev {
            if space_between(p, t, prev_unary) && !out.ends_with(' ') {
                out.push(' ');
            }
        }
        out.push_str(&t.text);
        prev_unary = unary;
        prev = Some(t);
    }
    out
}

fn is_closer(t: &Tok) -> bool {
    t.kind == Kind::Op && matches!(t.text.as_str(), ")" | "]" | "}")
}

fn bracket_delta(toks: &[Tok]) -> i32 {
    toks.iter()
        .filter(|t| t.kind == Kind::Op)
        .map(|t| match t.text.as_str() {
            "(" | "[" | "{" => 1,
            ")" | "]" | "}" => -1,
            _ => 0,
        })
        .sum()
}

/// Options du formateur (les valeurs par défaut suivent `[fmt]` de `project.air`).
#[derive(Clone, Copy)]
pub struct Options {
    /// Aligne les `:` des champs consécutifs d'un blueprint.
    pub align_fields: bool,
}

impl Default for Options {
    fn default() -> Self {
        Options { align_fields: true }
    }
}

/// Formate un fichier entier. `Err` si une chaîne n'est pas fermée (le fichier est alors laissé tel quel).
#[allow(dead_code)] // utilisé par les tests ; le binaire passe par format_with
pub fn format_source(src: &str) -> Result<String, String> {
    format_with(src, Options::default())
}

pub fn format_with(src: &str, opts: Options) -> Result<String, String> {
    let mut out: Vec<Line> = Vec::new();
    let mut stack: Vec<Block> = Vec::new();
    let mut brackets: i32 = 0;
    let mut blank_pending = false;

    for (n, raw) in src.lines().enumerate() {
        let toks = lex_line(raw).map_err(|e| format!("ligne {} : {}", n + 1, e))?;
        if toks.is_empty() {
            if !out.is_empty() {
                blank_pending = true;
            }
            continue;
        }
        if blank_pending {
            out.push(Line { text: String::new(), field: None });
            blank_pending = false;
        }

        // Première pièce de code (hors commentaire) de la ligne.
        let first = toks.iter().find(|t| t.kind != Kind::Comment);
        let leading_dedent = matches!(first, Some(t) if t.is("end") || t.is("else") || t.is("catch"));
        let mut level = stack.len() as i32 - if leading_dedent { 1 } else { 0 };

        if brackets > 0 {
            let closers = toks.iter().take_while(|t| is_closer(t)).count() as i32;
            level += (brackets - closers).max(0);
        } else if matches!(first, Some(t) if t.is(".")) {
            level += 1; // chaîne d'appels : `.map(...)` sur la ligne suivante
        }
        let level = level.max(0) as usize;

        let body = render(&toks);
        let is_field = stack.last() == Some(&Block::Blueprint)
            && brackets == 0
            && toks.len() >= 2
            && toks[0].kind == Kind::Word
            && !toks[0].is("fun")
            && toks[1].is(":");
        let field = if is_field {
            Some(Field { indent: level, name: toks[0].text.clone(), rest: render(&toks[2..]) })
        } else {
            None
        };
        out.push(Line { text: format!("{}{}", INDENT.repeat(level), body), field });

        // Met à jour la pile de blocs, token par token.
        let code: Vec<&Tok> = toks.iter().filter(|t| t.kind != Kind::Comment).collect();
        for (i, t) in code.iter().enumerate() {
            if t.kind != Kind::Word {
                continue;
            }
            let prev_is_else = i > 0 && code[i - 1].is("else");
            let next = code.get(i + 1);
            let in_trait = stack.last() == Some(&Block::Trait);
            match t.text.as_str() {
                "end" => {
                    stack.pop();
                }
                "if" if !prev_is_else => stack.push(Block::Plain),
                "unless" | "while" | "for" | "match" | "try" => stack.push(Block::Plain),
                "blueprint" => stack.push(Block::Blueprint),
                "trait" => stack.push(Block::Trait),
                // `fun nom(...)` ouvre un bloc ; la lambda `fun(...)` et la signature d'un trait non.
                "fun" if !in_trait && matches!(next, Some(nx) if nx.kind == Kind::Word) => {
                    stack.push(Block::Plain)
                }
                _ => {}
            }
        }
        brackets = (brackets + bracket_delta(&toks)).max(0);
    }

    while out.last().map_or(false, |l| l.text.is_empty()) {
        out.pop();
    }
    if out.is_empty() {
        return Ok(String::new());
    }
    if opts.align_fields {
        align_field_runs(&mut out);
    }
    let lines: Vec<&str> = out.iter().map(|l| l.text.as_str()).collect();
    Ok(lines.join("\n") + "\n")
}

/// Aligne les types des champs consécutifs (même indentation, sans ligne vide ni commentaire entre eux).
fn align_field_runs(out: &mut [Line]) {
    let mut i = 0;
    while i < out.len() {
        if out[i].field.is_none() {
            i += 1;
            continue;
        }
        let indent = out[i].field.as_ref().unwrap().indent;
        let mut j = i;
        while j < out.len() && out[j].field.as_ref().map_or(false, |f| f.indent == indent) {
            j += 1;
        }
        let width = out[i..j].iter().map(|l| l.field.as_ref().unwrap().name.chars().count()).max().unwrap();
        for l in &mut out[i..j] {
            let f = l.field.as_ref().unwrap();
            let pad = " ".repeat(width - f.name.chars().count());
            l.text = format!("{}{}:{} {}", INDENT.repeat(f.indent), f.name, pad, f.rest);
        }
        i = j;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn f(s: &str) -> String {
        format_source(s).unwrap()
    }

    #[test]
    fn indents_blocks_and_normalizes_spacing() {
        let src = "fun add(a:Int,b:Int)->Int\nreturn a+b\nend\n";
        assert_eq!(f(src), "fun add(a: Int, b: Int) -> Int\n    return a + b\nend\n");
    }

    #[test]
    fn keeps_ranges_unary_minus_and_calls_tight() {
        assert_eq!(f("x = -1\nfor i in 1 .. 5\nprint(-x)\nend\n"),
                   "x = -1\nfor i in 1..5\n    print(-x)\nend\n");
        assert_eq!(f("y = a - -b\nz = [-1, -2]\n"), "y = a - -b\nz = [-1, -2]\n");
        assert_eq!(f("print (x)\nreturn (a)\n"), "print(x)\nreturn (a)\n");
    }

    #[test]
    fn one_line_if_does_not_change_depth() {
        let src = "fun f()\nif a then b() end\nc()\nend\n";
        assert_eq!(f(src), "fun f()\n    if a then b() end\n    c()\nend\n");
    }

    #[test]
    fn else_if_is_one_block() {
        let src = "if a\nx()\nelse if b\ny()\nelse\nz()\nend\n";
        assert_eq!(f(src), "if a\n    x()\nelse if b\n    y()\nelse\n    z()\nend\n");
    }

    #[test]
    fn trait_signatures_have_no_end() {
        let src = "trait T\nfun run()\nfun stop() -> Int\nend\nx = 1\n";
        assert_eq!(f(src), "trait T\n    fun run()\n    fun stop() -> Int\nend\nx = 1\n");
    }

    #[test]
    fn lambda_does_not_open_a_block() {
        let src = "fun main()\nf = fun(x) => x*2\nprint(f(2))\nend\n";
        assert_eq!(f(src), "fun main()\n    f = fun(x) => x * 2\n    print(f(2))\nend\n");
    }

    #[test]
    fn comments_and_strings_are_untouched() {
        let src = "x = \"a  +  b #not\"   # reste   tel quel\n# seul\n";
        assert_eq!(f(src), "x = \"a  +  b #not\"  # reste   tel quel\n# seul\n");
    }

    #[test]
    fn collapses_blank_lines_and_trailing_whitespace() {
        assert_eq!(f("\n\nx = 1   \n\n\n\ny = 2\n\n\n"), "x = 1\n\ny = 2\n");
    }

    #[test]
    fn multiline_list_and_method_chain_are_indented() {
        let src = "xs = [\n1,\n2\n]\nr = xs\n.map(f)\n.join(\",\")\n";
        assert_eq!(f(src), "xs = [\n    1,\n    2\n]\nr = xs\n    .map(f)\n    .join(\",\")\n");
    }

    #[test]
    fn decorators_stay_attached() {
        assert_eq!(f("fun f()\n@native(\"x\")\nend\n"), "fun f()\n    @native(\"x\")\nend\n");
    }

    #[test]
    fn aligns_blueprint_fields_but_only_consecutive_ones() {
        let src = "blueprint P\nid:Int\nname : String = \"x\"\n\nage:Int\nfun f()\nx: Int = 1\nend\nend\n";
        assert_eq!(f(src),
            "blueprint P\n    id:   Int\n    name: String = \"x\"\n\n    age: Int\n    fun f()\n        x: Int = 1\n    end\nend\n");
    }

    #[test]
    fn alignment_can_be_disabled() {
        let src = "blueprint P\nid:Int\nname:String\nend\n";
        let r = format_with(src, Options { align_fields: false }).unwrap();
        assert_eq!(r, "blueprint P\n    id: Int\n    name: String\nend\n");
    }

    #[test]
    fn is_idempotent() {
        let src = "blueprint P\nname:String\nfun hi()\nif name == \"a\" then print(1) end\nend\nend\n";
        let once = f(src);
        assert_eq!(f(&once), once);
    }

    #[test]
    fn unterminated_string_is_an_error() {
        assert!(format_source("x = \"abc\n").is_err());
    }
}
