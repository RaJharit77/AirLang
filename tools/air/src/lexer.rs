//! Lexer *de ligne* pour le formateur.
//!
//! Il ne cherche pas à valider le programme (c'est le travail du compilateur) : il découpe une
//! ligne en tokens en reproduisant les règles du lexer de référence (`compiler/lexer.py`) qui
//! comptent pour l'espacement : chaînes (avec échappements et `{interpolation}`), commentaires
//! `#`, nombres (`1..5` reste « 1 », « .. », « 5 »), identifiants Unicode, opérateurs.

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    Word,
    Int,
    Float,
    Str,
    Op,
    Comment,
    Other,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Tok {
    pub kind: Kind,
    pub text: String,
}

impl Tok {
    pub fn is(&self, s: &str) -> bool {
        self.kind != Kind::Str && self.kind != Kind::Comment && self.text == s
    }
}

const TWO_CHAR_OPS: [&str; 10] = ["==", "=>", "!=", "<=", ">=", "->", "-=", "+=", "*=", "/="];

/// Découpe une ligne. `Err` si une chaîne n'est pas fermée.
pub fn lex_line(line: &str) -> Result<Vec<Tok>, String> {
    let chars: Vec<char> = line.chars().collect();
    let mut toks = Vec::new();
    let mut i = 0;
    while i < chars.len() {
        let c = chars[i];
        if c == ' ' || c == '\t' || c == '\r' {
            i += 1;
        } else if c == '#' {
            let text: String = chars[i..].iter().collect();
            toks.push(Tok { kind: Kind::Comment, text: text.trim_end().to_string() });
            break;
        } else if c == '"' {
            let start = i;
            i += 1;
            let mut closed = false;
            while i < chars.len() {
                if chars[i] == '\\' {
                    i += 2;
                    continue;
                }
                if chars[i] == '"' {
                    closed = true;
                    i += 1;
                    break;
                }
                i += 1;
            }
            if !closed || i > chars.len() {
                return Err("chaîne non fermée".to_string());
            }
            toks.push(Tok { kind: Kind::Str, text: chars[start..i].iter().collect() });
        } else if c.is_ascii_digit() {
            let start = i;
            while i < chars.len() && chars[i].is_ascii_digit() {
                i += 1;
            }
            let mut kind = Kind::Int;
            if i + 1 < chars.len() && chars[i] == '.' && chars[i + 1].is_ascii_digit() {
                kind = Kind::Float;
                i += 1;
                while i < chars.len() && chars[i].is_ascii_digit() {
                    i += 1;
                }
            }
            toks.push(Tok { kind, text: chars[start..i].iter().collect() });
        } else if c.is_alphabetic() || c == '_' {
            let start = i;
            while i < chars.len() && (chars[i].is_alphanumeric() || chars[i] == '_') {
                i += 1;
            }
            toks.push(Tok { kind: Kind::Word, text: chars[start..i].iter().collect() });
        } else {
            let two: String = chars[i..(i + 2).min(chars.len())].iter().collect();
            if two == ".." || TWO_CHAR_OPS.contains(&two.as_str()) {
                toks.push(Tok { kind: Kind::Op, text: two });
                i += 2;
            } else if "=<>-+*/.%?:,()[]{}@".contains(c) {
                toks.push(Tok { kind: Kind::Op, text: c.to_string() });
                i += 1;
            } else {
                toks.push(Tok { kind: Kind::Other, text: c.to_string() });
                i += 1;
            }
        }
    }
    Ok(toks)
}
