#!/usr/bin/env ruby
# frozen_string_literal: true

# airdoc — génère la documentation Markdown à partir des commentaires `##` des fichiers .air.
#
#   ruby tools/airdoc.rb stdlib/*.air            # écrit docs/stdlib/<module>.md
#   ruby tools/airdoc.rb --out docs/api fichier.air
#   ruby tools/airdoc.rb --check stdlib/*.air    # code 1 si la doc générée n'est plus à jour
#
# Ruby standard uniquement (aucune gem). Cet outil est facultatif : il n'est pas nécessaire
# pour compiler des programmes AirLang.

module AirDoc
  Item = Struct.new(:kind, :name, :signature, :doc, :example, :line, keyword_init: true)
  Doc  = Struct.new(:title, :intro, :items, keyword_init: true)

  DECL = /\A(?:export\s+)?(?<kind>fun|blueprint|trait)\s+(?<name>[A-Za-z_]\w*)(?<rest>.*)\z/

  # Découpe un fichier en blocs `##` collés ensemble, puis associe chaque bloc à la déclaration
  # qui le suit immédiatement (une ligne vide détache le bloc : c'est l'en-tête du module).
  def self.parse(source, fallback_title)
    header = []
    items  = []
    block  = []
    seen_decl = false

    source.each_line.with_index(1) do |raw, lineno|
      line = raw.chomp
      if line =~ /\A\s*##\s?(.*)\z/
        block << Regexp.last_match(1).rstrip
        next
      end

      if (m = DECL.match(line.strip))
        # Une déclaration indentée (méthode de blueprint) est ignorée : l'API publique est au niveau 0.
        if line =~ /\A\S/
          seen_decl = true
          items << build_item(m, block, lineno)
        end
        block = []
      elsif line.strip.empty?
        header.concat(block) unless seen_decl || block.empty?
        block = []
      else
        block = [] unless line.strip.start_with?('@') # un décorateur peut séparer doc et fonction
      end
    end

    title, intro = split_header(header, fallback_title)
    Doc.new(title: title, intro: intro, items: items)
  end

  def self.split_header(lines, fallback)
    title = fallback
    intro = []
    lines.each do |l|
      if (m = l.match(/\AModule\s*:\s*(.+)\z/))
        title = m[1].strip
      elsif (m = l.match(/\AImport\s*:\s*(.+)\z/))
        intro << "Import : `#{m[1].strip}`"
      else
        intro << l
      end
    end
    [title, intro.join("\n").strip]
  end

  def self.build_item(match, block, lineno)
    text, example = [], []
    block.each do |l|
      if (m = l.match(/\AExemple\s*:\s*(.*)\z/))
        example << m[1]
      elsif example.any? && l.start_with?('  ')
        example << l.strip
      else
        text << l
      end
    end
    Item.new(kind: match[:kind], name: match[:name],
             signature: "#{match[:kind]} #{match[:name]}#{match[:rest]}".strip,
             doc: text.join(' ').squeeze(' ').strip,
             example: example.join("\n"), line: lineno)
  end

  def self.markdown(doc, source_name)
    out = +"# #{doc.title}\n\n"
    out << "#{doc.intro}\n\n" unless doc.intro.empty?
    out << "> Généré par `tools/airdoc.rb` depuis `#{source_name}` — ne pas modifier à la main.\n\n"
    doc.items.each do |it|
      out << "## `#{it.name}`\n\n"
      out << "```air\n#{it.signature}\n```\n\n"
      out << "#{it.doc}\n\n" unless it.doc.empty?
      out << "```air\n#{it.example}\n```\n\n" unless it.example.empty?
    end
    out.rstrip + "\n"
  end

  def self.run(argv, io: $stdout)
    out_dir = File.join('docs', 'stdlib')
    check = false
    files = []
    until argv.empty?
      case (a = argv.shift)
      when '--out'   then out_dir = argv.shift or abort('--out attend un dossier')
      when '--check' then check = true
      when '-h', '--help'
        io.puts 'Usage : ruby tools/airdoc.rb [--out DIR] [--check] fichier.air ...'
        return 0
      else files << a
      end
    end
    abort('Erreur : aucun fichier .air donné (ruby tools/airdoc.rb stdlib/*.air)') if files.empty?

    stale = 0
    files.each do |f|
      base = File.basename(f, '.air')
      md   = markdown(parse(File.read(f, encoding: 'utf-8'), base), f)
      dest = File.join(out_dir, "#{base}.md")
      if check
        current = File.exist?(dest) ? File.read(dest, encoding: 'utf-8') : nil
        (stale += 1; io.puts("périmé : #{dest}")) unless current == md
      else
        Dir.mkdir(out_dir) unless Dir.exist?(out_dir)
        File.write(dest, md)
        io.puts "écrit : #{dest} (#{parse(File.read(f, encoding: 'utf-8'), base).items.size} entrées)"
      end
    end
    stale.zero? ? 0 : 1
  end
end

exit(AirDoc.run(ARGV)) if $PROGRAM_NAME == __FILE__
