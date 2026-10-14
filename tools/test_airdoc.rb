# frozen_string_literal: true

require 'minitest/autorun'
require 'stringio'
require 'tmpdir'
require_relative 'airdoc'

class AirDocTest < Minitest::Test
  SRC = <<~AIR
    ## Module : demo
    ## Un module d'essai.
    ## Import : import demo

    ## Additionne deux entiers.
    ## Exemple : demo.add(1, 2)  # => 3
    export fun add(a: Int, b: Int) -> Int
        @native("air_add")
    end

    fun hidden()
    end

    ## Commentaire détaché (ligne vide ensuite)

    blueprint Point
        x: Int
        fun move()
        end
    end
  AIR

  def test_header_title_and_import_are_extracted
    d = AirDoc.parse(SRC, 'fallback')
    assert_equal 'demo', d.title
    assert_includes d.intro, "Un module d'essai."
    assert_includes d.intro, 'Import : `import demo`'
  end

  def test_documented_function_has_signature_text_and_example
    add = AirDoc.parse(SRC, 'x').items.find { |i| i.name == 'add' }
    assert_equal 'fun add(a: Int, b: Int) -> Int', add.signature
    assert_equal 'Additionne deux entiers.', add.doc
    assert_equal 'demo.add(1, 2)  # => 3', add.example
  end

  def test_only_top_level_declarations_are_listed
    names = AirDoc.parse(SRC, 'x').items.map(&:name)
    assert_equal %w[add hidden Point], names # `move` est indenté : pas d'API publique
  end

  def test_markdown_is_stable
    md = AirDoc.markdown(AirDoc.parse(SRC, 'x'), 'demo.air')
    assert_match(/\A# demo\n/, md)
    assert_includes md, "## `add`"
    assert_equal md, AirDoc.markdown(AirDoc.parse(SRC, 'x'), 'demo.air')
  end

  def test_check_mode_detects_stale_docs
    Dir.mktmpdir do |dir|
      src = File.join(dir, 'demo.air')
      File.write(src, SRC)
      out = File.join(dir, 'out')
      io = StringIO.new
      assert_equal 1, AirDoc.run(['--out', out, '--check', src], io: io) # rien d'écrit encore
      assert_equal 0, AirDoc.run(['--out', out, src], io: io)
      assert_equal 0, AirDoc.run(['--out', out, '--check', src], io: io)
      File.write(src, SRC + "\n## Nouvelle.\nfun more()\nend\n")
      assert_equal 1, AirDoc.run(['--out', out, '--check', src], io: io)
    end
  end
end
