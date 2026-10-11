# Убирает из текста личное: папку проектов (обе записи: с / и с \) вместе с разделителем
# после неё и имя автора. Зовётся из publish_github.sh как perl -p (для файлов и для
# сообщений коммитов); строки приходят через окружение, \Q...\E экранирует их целиком.
#
# Имя - PRIVATE_NAME: основы через | (из `git config publish.privateName`). Основа кириллицей
# меняется на «автор» в том же падеже (окончания -й, -я, -ю, -ем, -е), латинская - на
# «the author». Само имя в этом файле не пишется.
BEGIN {
    $fwd = $ENV{PRIVATE_DIR};
    $bck = $ENV{PRIVATE_DIR_BS};
    @names = grep { length($_) >= 4 } map { my $s = $_; $s =~ s/^\s+|\s+$//g; $s } split /\|/, ($ENV{PRIVATE_NAME} // '');
    %ru = ("\xd0\xb5\xd0\xbc" => "\xd0\xb0\xd0\xb2\xd1\x82\xd0\xbe\xd1\x80\xd0\xbe\xd0\xbc",   # -ем -> автором
           "\xd0\xb9" => "\xd0\xb0\xd0\xb2\xd1\x82\xd0\xbe\xd1\x80",                             # -й  -> автор
           "\xd1\x8f" => "\xd0\xb0\xd0\xb2\xd1\x82\xd0\xbe\xd1\x80\xd0\xb0",                     # -я  -> автора
           "\xd1\x8e" => "\xd0\xb0\xd0\xb2\xd1\x82\xd0\xbe\xd1\x80\xd1\x83",                     # -ю  -> автору
           "\xd0\xb5" => "\xd0\xb0\xd0\xb2\xd1\x82\xd0\xbe\xd1\x80\xd0\xb5");                    # -е  -> авторе
}
s/\Q$bck\E\\?//gi if length $bck;
s/\Q$fwd\E\/?//gi if length $fwd;
for my $n (@names) {
    if ($n =~ /[\xd0\xd1]/) {
        s/\Q$n\E(\xd0\xb5\xd0\xbc|\xd0\xb9|\xd1\x8f|\xd1\x8e|\xd0\xb5)/$ru{$1}/g;
        s/\Q$n\E/\xd0\xb0\xd0\xb2\xd1\x82\xd0\xbe\xd1\x80/g;
    } else {
        s/\Q$n\E/the author/gi;
    }
}
