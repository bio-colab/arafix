"""
معجم نواة خفيف مضمَّن — لحسم انقلاب لام-ألف **المُبهَم** الشائع.

الفلسفة
--------
النواة ترفض التخمين الإملائي العام. هذا المعجم **استثناء مقصود ومحدود**:
كلمات عربية شائعة تُستعمل فقط كشاهد ثنائي عند مبادلة «ا/ل» المشتبهة
(انظر ``arafix.lamalef``): تُقبل المبادلة إذا كان الأصل غائباً عن المعجم
والمرشَّح حاضراً فيه.

- بلا تبعيّات: ``base64`` + ``zlib`` من المكتبة القياسية.
- تحميل كسول: لا يُفك الضغط إلا عند أول استدعاء لـ ``get_core_lexicon``.
- المصدر التاريخي: قائمة كلمات عربية مضغوطة (انظر CHANGELOG / add/).

الاستعمال
---------
::

    from arafix.lexicon.core import get_core_lexicon
    vocab = get_core_lexicon()
"""

from __future__ import annotations

import base64
import zlib
from functools import lru_cache

__all__ = [
    "COMPRESSED_LEXICON",
    "get_core_lexicon",
    "core_lexicon_size",
    "clear_core_lexicon_cache",
]

# base85(zlib(utf-8 words joined by newlines)) — ~7.2KB on disk, ~1.7k entries.
# Curated 2026-08: removed mechanism-dead entries and non-Arabic intruders,
# added gold-attested protection words, high-frequency repair targets, and
# both-sides coverage for valid transposition pairs (ثالث/ثلاث، خالف/خلاف…).
COMPRESSED_LEXICON = """c-nPbS%TZRuKo9}Q=Sy}>m+@5P&e&RQQ20h<RS7(T)Vj>NC4+hejlmu9C0225a#2*pQ}fBbc=@sKEG&St%1$r@$+$1&Vrvy1iJ)IF}V8t^0^ftUtS<sA}PqFBJn%H^XF2s`Rfr9yvWzTQt<ZqC4I^K<Q2-nZ4Rz6ih$1z!)*mMlMMfkAT~iW*FO1aT@f4GSQ!eWbO+V9oKqtm-9s>^YCboT`7UL@f3))Lo`TXdkJl6&wMG_9y$K+7-rhQ|K<T{45rVnX4W=6GW5<@EvS4a}0g99xxA*?HV6Kn>il!Bsv>Pp`6}oF3!sFMY({7I+9~bRy04YssP3KdBVD&v!EyI-Wia=^zhHFZz?F(^QLwyY7G6CjvM&t>M#NP>yu@Ofp=ywG_zbnyuH4~Jce@qHXmui8Dx>JHUNY7v%xlCEx5?BjdYK0TE&6Gfh>;oNm<^`W>!KYL3SrUBc0}p+i>#@L{)KGfBXM(T8)ItA!w0SjT&`C8kD3uWK79$M`P89S=5u|m8aObd(S+oiUEOd;~8ZWp&%h#rl0+}-g)($*H92NjO2vS~H%DRkh23GGB^hm~T;)ojCU=%9B^8fkx6-zMCT0nM>H-|k0wc-Upa_PVWKq>asiJP}3!6|Q&1<EXW1xR_P4HhaGzg-n{sa%=C0^hLeZ#pX^=v9BKE0+l??~QBomTIH@{PS^;Io&!OAn2JK9v_&=A&!pCj0n9e4k<UUT!D~LB#sETF=v1c6%(P?CoeaJM>&gj-ap6G7LR`P@i@xbctZ%_9jkYgfrm^6T?`3);J_VIA9!7la)_-Rt{A4R?~1TT;3ekc*Wr!}*_G``;K>5A%M1=X559X4A`G8j5$p)~3j4{sOoCU;=7zP)(7*bYxMF##BE0)gGX5PwC_6%ky2GM&I9q$HRRZv(g&;?RY1{Lp?S1b{VB>w)bA>Y;0CF}odI?%>-to&j2Cb|#Gp}C9LF#`*I1#|sW#TtM9M&N&9>^-K(ysch6xIMp%)G~hJtyg(M2<O7Ssxxe$1h(TUT~isd_fJ|Ggm4iNrt`@2U)0Inx91laM}ht`6Fd!z{DAYza4CGA|wc)!NcW)m-rYDGMH^?k4bZJLZXY)g<^~ZyeA6e$TwU$W0AaDCtBR)1mXx9ftj}6E2A86Qw2GC7fX0YIJo?;WbZ+!EbY!CuK5wSv=O(ok<Y^sd+U}?82ly#roAP-$Kga3@ToZ_vCqK@kMRWI%!@D<;yo<W=#?O*-Qa8;vtFj4dHh5`RcmnbP0)K3C%~Dvku#s7=cFD#E)EC&3VX^qio|eo6{XH0tbj95`Lw8E^SZ<>;f257J?$lGEdW*!^kKX3Y!ZlD%!Rk@3y$$Mp0ZyZP=l{5pWOHe5$Jt>lWF}0U`!43;3n$3!>si=T;WQd_)yERcQ~MUF>%QmzBv5gtj@ULr#u`EuN?W0&%cRfoCv++#4_O>H=+2SVed_k5K}gs>yBEA!+7Vd=`K4Z)b`H8-JN?WscbC)iY$8^W=5Ny=+5b60b+oPCK#*g;*JxT<Z68q!313tA-B#6NN<B0gG=ad)<J*DavH3$avr7?0pHU^zB%kU^#GfIK*(z3s23Z_q{2gx#L7bac8Jp@!p5^%W=X%O@HORmB=Q}OvPiU^<q{OA2xzR9u@MKDSf5L;`6{1x74)j4Y14QItYpXj?QnwC6#w0^w^p`B#R3U!S;>%jI!v>M13yEkUWQOTB`|N4X)?qdcCdHIH2LCbts1EkA8w6MVi%VQ6eUL)#i1N<NY`MOF@jQV@EZi*e6R%Ix88#T1Yunlcm)`nyyU`#!nzg$iz*cNiIO`cM-QUH6yZb_gLXl;K~6Z(EVxFv#pSl91FygXK`gC-N~PJ2`8HT4mAJ!HsE}nyJ*dQ!IMi7PJWzz<7Ktky;>qfOUAZCsxY#7<dz3-bUnkyt1KNlJI3k34Z)6ADAUxpLa~x!V7p{mv@0ZQv4}brIoxkyQxe;mM#o?CHkuX@G3Ro#B2ul(6xZ<}WE!ce9dZ%tF6>s2MOhNM^75&RIk;C1qMte__4Q~!nZYgk$&{cMYSZ<QHI7TL(#KCFSWGx9Hfe8Sgx{U}+@O`4fWKZu1dbh*mwL2GsvB$6>N<58)1+K&ZL4~f!CLzRE1XM~D5j!c)O;L`O*x}ghl8T4WO|22QMkhyj$#b6-5ic_nJ;L6**P!MM1SCOCLawPGm~X5y?6N`8;l+2veRYMCDO`a2Y{2(&-=yvqnT)Op?sz8dMeAxAejt>K9&fu5-g=-g;ehQg5UX~`tBMkpTSd=Wc9)*vRiR%D6$r9qf*r2gz29#kv0?&j8U=di9c9matspijQ@?QL@6|+#?L48CUoS2%4jU{MjE{SnX9MQm^YHh$s~g1cVCPS8!Y1`7`|Oix(Dm#BJ@5B=$lpEX!0TsFvv&%P*yDrffHuH`3~*aPFVhIfTPd99Vj%Z8BZ|`d+O)Kvo0j%$P1>uiNbb%K9FOLChH(bqEGDu}T4=8Q<Qw!p@AdFC3ASk<DKAvJ=+e6)W=X1|J&$ue)y_QC&N4gb`+(Ix%UA2cY-@q&7v6X-d9pej2-<xqLdvdO(L)QbJPWRH@$7{6QGu9Xz}a|{B7Y+s2w>h~RPlM?m(mV>51+(|;J3pL#l}p$S47sOoj71s$x34o+cu%5y)VWW&!4B$R8OaAKAom#)5&kK5n?~x(*>F5a;J_dri}wYG;QqXrj0~hV5UTf<CG2Z9$Cx}){7B#+0c&}zR=KR`+;?hLa&k$p2Jc^(cYDtz1U@afMSxRC;|=aN=$lg*#$#`7=4S;*42!3!jk}1Cq(G2U6%{$8@7c=&Pk>nS7L<oC%Hwz{E(UP=Agr|FA(!j)T!E5YK<xre{c?LXss0ZQ9;h~AUpTRjPR}m3M-h5J1d8M8O)Jmy>s<O?vs%YD<?3AGi)}jq9yp^*B%Kj=QZ6HhaMa0E!s`@>C~f>*a^>LhZg(<d+)Jb5ecAIg~Emzfms#`HkC-;NJ?}95=xsVhalLn%ajomqqP7ZDv9W%9lx}EqB!1&yG^FRUqcAg;{q!hse8Rb=)4ioc_ZD*9WWDtx=9%Ht`Dqp7<>}L+h~M0hg6j?S5*S5Dh5$JM$$7DL&3U&nCJ~Jrvhs^fmNDN>o7oImNUgBJX37KT$2%RI4ScmBkEWKix{C+Qp^eO@uwoZpKHH8BUg2-^;4owwtG@hA#XFnyXNS#hn!pj>rjE+Q3AT01a>(I>~a#=<s_)fNnn?gFjud{hp>)Q2yEu5i1brM_<TLp+eGcYXylGd!=M^D0z0$>bZ7~z^99uT0y>-ob~p*F{ss3k39Q-~#EO$!N2pyl649YXErc|Ea-#P-556Ih<3nJrF3gp<fbI=}9T5Wi1%z683v=Zyu=19DK7YxM@dYV66Ekd4X3o?bUJen3{WzA@-eLv1?0My#Fp99!K1+N;Sv=Ib=Kn);VS@-luSku&@)C7M>i|)l8)+-WjTY}gl$v$eR7-s7gFEZTLUCn`tP0|tj9qwv+EiU2leMS3BGuKgUeJuBR9j_V?ji@GW|iP`CKKJ9n&m{YZtYWSR8z|sqxe9rxIr)=Gh0M>Zi@))UlL|>hxNZOHzx%4H3@D=2<&GP*s&y_V@W`7k-+wb1Z6uCfvH1sz<x5qD+?6n2L2_19YaFx36hALOfQfQE<W;Poe1a=64>J-Zn)Vy!}l{Is#s|G4D6#3>IF*XgizZLGSOpmjKD%GD?=vWiqZ(*MyDe6t$~n^>np;mK9yDCF?g;`^<10gbB)XjVQy9k=n@j@{o~H($Gs^1EfDDO8`uHETQ7S_2LtZ}Mb}=mB9X#)VCx9zq7m51qH^>PVzy{O=n?`anGwes0i9;#gakM~1~ia7p}Z|GUUl$=2x8Fqg%w-oBgp%7S+?z0C*B~v=esID1$jZ@1G{Baw#-*2CM^4j(Iq@Lx&-%wfc$GgfSnEk9si_Vf=(#s!;!xgf^+Wj_T$6=L39!bb0>k|H~PVE^n>4k1-`@&d@mpHUOwP;J5+m9q{la`HXmyOTTo4fIO4=Mi_VOwvpu0Xf+%lAWeUo~xi0Tg6Mrf~=Hr#J&3jx`C)($nph_w=%gsk+Q#Qy~B(_foItk}CsqoAumB>?WkP~w4gTplP$X52IOdWZcuB0j?g6IFHI;6x%MVn_L4%GG8mJ3~~u4>e7_5>4xOgPC!ffTgb*cI3jA)vcKU|)cMm-2zH-2>mV2ftVkc-bBBvOD1Ib*N2ZVQvx&Y|3i0m#~-GqBPjzb$$yH<MIjRWn}t>;7))e-nF_0^}86r9{*zfy5jIg)Fdu-NEJz;1*o0b*(UU^M7}gGje5&}3224hvbBhScb5_zSzBjt_FV_#t=Nak_d_{z3^ur9S|@mVqP(1=9{AcjM_vMS3x32M=g51_vC0N}^_YLwsNdwL$*wwOcrjRPl>{#UbSa%`Yl#w=GXM59!yPxR&&FA;WY0a?m#IHg(9;jOkq$>p|54gphJSqgEB*CDVQ@FyQEaIB7nd1gz9WkN1z1#7jsT(wkTk84rGs;9(Nfp9l3CXva72sh>>l)r<9x$b-LUyL+%#`$WUip*NqhMpY{HZW%<D6u^i+W6Yf$qw;`1LSz9amG*{!*-1H&E%e9C=cU$OZa90=4=!Rj*U55FmfU*htwj)Ac6Yc8FeQGR6nQbA39$5Fh)iYqJpNWgZOLX5TmBavrU-b#xlB<CAv-WTY+BzoKYC}5;>Ba>xl6qJ!Jmn>=@D9akYbrpaOu#CkoZ$@s_3x0ox8-#38)QS{<-$tq5Zbo1nJ$w|HcdZdtowfLF<1tJpk^)SC`*MT_+V&E`@R+3rq8OI9Bs|MeoW32}R%A)eWfYCTm0IAMVr19w8O1~%+NBj;h;;?|ds}qZ0+0OlC?a`RQxxZeOR(WvgBi_!y3eJj-bA>AkrD;+!Y$l^SmjXXQ{1a`n=0Fhc>VffkMING7WU_~;d6&J7`6CkYV8|6J}I(JtaTBUr0tt>mQIUW7T@3_7M1i2{-E^iM(fXrq;7A~L8nFcmKJ?LTJ-N|`F^E^-#veID0d1i|K70WAHKEqZ{6DZw_a`iJExX^H`LZY6>9Ov4=w*HphdU-7Cq}*^qz0gX}(4G#xw-&GrzO;xqnw%dw8|v&IB>crKhdEE84klMEl%tp{*~>TYWI3t#5r>wDh)fdu(gAOsZ$V-kK@+?OcCsS(j;RL9%5TtYxvPWud99#fWx(oM-B80Z(_==}*U9J70{gis7y694#sstqaPniHutVIa|=}S}0C;1n-iv1If!htv{AyLE=3R*|VM~fu{3;z6ZJ<>3Oa0F|BT6=@E*%=KnY^<SuR~OMR2;3maAY`6C~zaXkKswTt3+SBPy6?mT6>Ra?25v=B4)DW)s09#tAA!QApn0qx3M`0ByrytQ4_YH6p(&H}a5&Yu<_y|mLemOwe}vOz<4!!Di^r=s_X#&3%2o2jmUEl`6k!SpbWO)67jAt=dws;Qp3^`OWypx=^iOL}dVOyYVy=<tGCdoVNWmO!e_!Ji8{_$yNfpV6e&8c20NYHUz+OVB_6w!r5%4R(129KBLUtdfFV38vPlitIV(c5CqO&wnH-R8>3TSWG~vCN3xypN3ROQKA>9O`l9v-7HjSTet>Y0uodAhm${`MEW#rff|%HpR|G}AA%FUX#`sL>GOvODtSBHrqH73OmfzO0<Oxplnt6VXyKrNFKTssP$74LS~+Os7EB|dKpF%fB?q<r!{o^=g4p*W{^oU6^!k+4f~gGE_qPztk%|&j0vfvr$DsSm@B531aVbgl5E|7#8G@3F@AMXgNO_A=@C~DVcOb@u(MP~e3@{&@akS390Kr8o2ags=$t;*QnF8`$RUoUwj?;^7tqT_b;jOgFJVB<3OKjij^FQf-eM!!Y6F2Pn0zUt*1e5e=mJ735n8<n4>7P!|oeuUNWzASYhKg)eK9oRGEmI;>h`?;&CW`=3a+4-)$dsK)^biB91ehSq{9vXBGdoyNQfm<TTpmg-V1UqImyR6=8_Pi8mH>a-8SrT91zR=1qA~ea2!;(XYJfq5j2ULgxZ{WykY89c^Tu6kanCpEMMh22TDHV{mK$Pm5oYxlgR&U_+%Eh!!GpgoSSBsN{H@HWav-E<z0BxR0{Z*#L5Xt-#HAAh<sHR^T3h18w&33y>`K7m$p~pM_Cg6Z&Nex2=gCwGiKAGycn^NhNtg2D#XMkU;wgb4PM?{j$K+5ANG|rqr3JST#3(xmLUyU;OVub-{G`x)=#bzqK<M`q^dp1fSbxur$u99P3PQ=PTg=>d$c4hBm>0PNflC9rApo5MY^PvH6ho0el_$_2g)`V|P~RgfP@O6Z>?LzkiAyk>wF*d2!dNhG=LM>(OM$8e7pPiqhW40*!7F^zp<mI{2?Z`a;u@oQ9YtyOpj<*Kg!tB7x{6l%Q)|(!4Yp-$>9^4W{bz9nst00$BR0f;*i@kYFiD|JJo;%2!BXQrw%k4W3*5=zmm0ehw!w>!1A9|fHc+*Inqx2!D<sf`5h!&x1d2LD9py$!sM9NJK9wCbL+}?V1Z($3Ua_C>K2`|TYX$H<nNU<&Uxl;|>y?N{r5wwsuFLNFukM2SZMz_gnwWVL@g;+DaHx8x0s9!&!`35g7x0`eJf#b^VEG-58XOR$)26_<dEXam+0*sEE}CJmpyp>FXL0aoZgB={b7g4;D>GP_D=6itvAO)br}PKfoXOrCfeN1<)Smg{kyQSwjL`yn17wvhup?L+4Yq2sQ-h6~?9*VI_MnWUgPgJ2tSfspLr<BF*9t@u0xLFHu+4f6hH5fW+oQ=l3928Q1L4(R4aVv%ft<n(*$Q$ASzw4#%BIYe*M+<vF_?s#ZNp+6kzZoyZAk1mSXgT4PVN{*z=%aPV%hyE3uY}a4_5<ELYFVF7dI#bG`J5pA_PbV>?&N|q1GpF4W25HMx&vpZ58J1`FU3(>;P}7$3KDi!0hxfOo!ecd}-2Pk7@P&M<nvHZ)Q&|0@X9TIxs1rnZ1T)l!*>aWinU7#fPSP9tw!EdpGnxl0kLSa{?o)iyaXJA*(gkY)#o<8ht4Ri2V485nE5|k3kq=vPM(=sND$_Kbp#zUlTZjG~4-SxfNk;!C!qErA~N2pvm9p9rtCh0Q^kNC=*_q>RO;CurB-~t7oLw2Y(u6)CfUv$yXBPkLHQT>N65bgtntd(p0`qg+N<sMZuao-~rz}@%$;I)wuVF)g*E2P9aS6X~==2KoftO*$s#7s+d2XcFpWYLte<yUF+h|uc3^}zQ}#lFjr0<^S-9nC{3PTZheoy^sEN;EC5MIZ0dfm`rHnv#_XW-S`Ks_P0Nc1p~Jw=kxsV;3><VrEB-m4v^M3nC=Ezrdt}G%a!Ww8zs3ep4{5*Ttwz8_Q4Myb09OE;GT*-CFL3%c`ZL+$%Mky3ql=gCPW>mH`q?lXWuYIjk>6tX|Bwi^1z~6RWo2HA6tMgJuKfQ1I*WUn"""  # noqa: E501


@lru_cache(maxsize=1)
def get_core_lexicon() -> frozenset[str]:
    """
    تفك ضغط المعجم المضمَّن وتُرجع ``frozenset`` غير قابل للتعديل.

    النتيجة مُخبَّأة (استدعاء واحد فعلي لكل عملية). أفرغ الخبيئة بـ
    :func:`clear_core_lexicon_cache` في الاختبارات إن لزم.
    """
    raw = base64.b85decode(COMPRESSED_LEXICON.encode("ascii"))
    text = zlib.decompress(raw).decode("utf-8")
    words = {w for w in text.split("\n") if w}
    return frozenset(words)


def core_lexicon_size() -> int:
    """عدد المداخل بعد التحميل (يُحمِّل المعجم إن لم يُحمَّل)."""
    return len(get_core_lexicon())


def clear_core_lexicon_cache() -> None:
    """للاختبارات — تُفرغ خبيئة التحميل الكسول."""
    get_core_lexicon.cache_clear()
