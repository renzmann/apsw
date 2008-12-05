# Python

# Extracts rst function comments and dumps them to a file

import sys
import os
import re
import urllib2
import urlparse

if len(sys.argv)!=3:
    print >> sys.stderr, "You must supply input and output filenames"

if os.path.exists(sys.argv[2]):
    os.remove(sys.argv[2])

op=[]
op.append(".. Automatically generated by code2rst.py")
op.append("   code2rst.py %s %s" % (sys.argv[1], sys.argv[2]))
op.append("   Edit %s not this file!" % (sys.argv[1],))
op.append("")
if sys.argv[1]!="src/apsw.c":
    op.append(".. currentmodule:: apsw")
    op.append("")

funclist={}
def do_funclist():
    baseurl="http://www.sqlite.org/c3ref/funclist.html"
    page=urllib2.urlopen(baseurl).read()
    funcs=re.findall(r"""<a href="([^'"]+?/c3ref/[^<]+?\.html)['"]>(sqlite3_.+?)<""", page)
    for relurl,func in funcs:
        funclist[func]=urlparse.urljoin(baseurl, relurl)
        # ::TODO:: consider grabbing the page and extracting first <h2> to get
        # description of sqlite3 api

def do_mappings():
    consts={}
    pages={}
    baseurl="http://www.sqlite.org/c3ref/constlist.html"
    page=urllib2.urlopen(baseurl).read()
    vars=re.findall(r'<a href="([^"]+?/c3ref/[^<]+?\.html)["]>(SQLITE_.+?)<', page)
    for relurl, var in vars:
        # we skip some
        if var in ("SQLITE_DONE", "SQLITE_ROW"):
            continue
        pg=urlparse.urljoin(baseurl, relurl)
        consts[var]=pg
        if pg not in pages:
            pages[pg]={'vars': []}
            # get the page title
            page2=urllib2.urlopen(pg).read()
            title=re.findall(r"<h2>(.+?)</h2>", page2)
            pages[pg]['title']=title[1]
            if pg.endswith("c_dbconfig_lookaside.html"): # duplicate description
                pages[pg]['title']="Database Configuration Options"
        pages[pg]['vars'].append(var)

    maps=mappings.keys()
    maps.sort()
    for map in maps:
        op.append(".. data:: "+map)
        op.append("")
        # which page does this correspond to?
        m=mappings[map]
        pg=None
        for val in m:
            if val=="SQLITE_OK": # present in multiple mappings
                continue
            # check that all values in mapping go to the same page
            if pg is None:
                pg=consts[val]
                op.append("   `%s <%s>`_" % (pages[pg]['title'], pg))
                op.append("")
            else:
                if consts[val]!=pg:
                    print "These don't all map to the same page"
                    print map
                    for val in m:
                        print "  ",consts[val],"\t",val
                    sys.exit(1)
        # check to see if apsw is missing any
        for v in pages[pg]['vars']:
            if v not in mappings[map]:
                print "Mapping",map,"is missing",v
                sys.exit(1)
        vals=m[:]
        vals.sort()
        op.append("    %s" % (", ".join([":const:`"+v+"`" for v in vals]),))
        op.append("")
        
    

# we have our own markup to describe what sqlite3 calls we make using
# -* and then a space seperated list.  Maybe this could just be
# automatically derived from the source?
def do_calls(line):
    line=line.strip().split()
    assert line[0]=="-*"
    indexop=["", ".. index:: "+(", ".join(line[1:])), ""]
    saop=["", "Calls:"]
    if len(line[1:])==1:
        saop[-1]=saop[-1]+" `%s <%s>`_"% (line[1], funclist[line[1]])
    else:
        for func in line[1:]:
            saop.append("  * `%s <%s>`_" % (func, funclist[func]))
    saop.append("")
    return indexop, saop
             

def do_methods():
    # special handling for __init__ - add into class body
    i="__init__"
    if i in methods:
        v=methods[i]
        del methods[i]
        dec=v[0]
        p=dec.index(i)+len(i)
        sig=dec[p:]
        body=v[1:]
        indexop, saop=[],[]
        newbody=[]
        for line in body:
            if line.strip().startswith("-*"):
                indexop, saop=do_calls(line)
            else:
                newbody.append(line)
        body=newbody
        for j in range(-1, -9999, -1):
            if op[j].startswith(".. class::"):
                for l in indexop:
                    op.insert(j,l)
                op[j]=op[j]+sig
                break
        op.append("")
        op.extend(body)
        op.append("")
        op.extend(fixup(op, saop))
        op.append("")
    
    keys=methods.keys()
    keys.sort()

    for k in keys:
        op.append("")
        d=methods[k]
        dec=d[0]
        d=d[1:]
        indexop=[]
        saop=[]
        newd=[]
        for line in d:
            if line.strip().startswith("-*"):
                indexop, saop=do_calls(line)
            else:
                newd.append(line)

        d=newd

        # insert index stuff
        op.extend(indexop)
        # insert classname into dec
        if curclass:
            dec=re.sub(r"^(\.\.\s+(method|attribute)::\s+)()", r"\1"+curclass+".", dec)
        op.append(dec)
        op.extend(d)
        op.append("")
        op.extend(fixup(op, saop))

# op is current output, integrate is unindented lines that need to be
# indented correctly for output
def fixup(op, integrate):
    if len(integrate)==0:
        return []
    prefix=999999
    for i in range(-1, -99999, -1):
        if op[i].startswith(".. "):
            break
        if len(op[i].strip())==0:
            continue
        leading=len(op[i])-len(op[i].lstrip())
        prefix=min(prefix, leading)
    return [" "*prefix+line for line in integrate]

do_funclist()

methods={}

curop=[]

cursection=None

incomment=False
curclass=None

if sys.argv[1]=="src/apsw.c":
    mappingre=re.compile(r'\s*(ADDINT\s*\(\s*([^)]+)\).*|DICT\s*\(\s*"([^"]+)"\s*\)>*)')
    mappings={}
else:
    mappings=None

for line in open(sys.argv[1], "rtU"):
    line=line.rstrip()
    if mappings is not None:
        m=mappingre.match(line)
        if m:
            g=m.groups()
            if g[2]:
                curmapping=g[2]
                mappings[curmapping]=[]
            else:
                mappings[curmapping].append(g[1])
            
    if not incomment and line.lstrip().startswith("/**"):
        # a comment intended for us
        line=line.lstrip(" \t/*")
        cursection=line
        incomment=True
        assert len(curop)==0
        if len(line):
            t=line.split()[1]
            if t=="class::":
                if methods:
                    do_methods()
                    methods={}
                curclass=line.split()[2].split("(")[0]
        curop.append(line)
        continue
    # end of comment
    if incomment and line.lstrip().startswith("*/"):
        op.append("")
        incomment=False
        line=cursection
        if len(line):
            t=cursection.split()[1]
            if t in ("method::", "attribute::", "data::"):
                name=line.split()[2].split("(")[0]
                methods[name]=curop
            elif t=="class::":
                op.append("")
                op.append(curclass+" class")
                op.append("="*len(op[-1]))
                op.append("")
                op.extend(curop)
            # I keep forgetting double colons
            elif t.endswith(":") and not t.endswith("::"):
                raise Exception("You forgot double colons: "+line)
            else:
                if methods:
                    import pdb ; pdb.set_trace()
                assert not methods # check no outstanding methods
                op.extend(curop)
        else:
            do_methods()
            methods={}
            op.extend(curop)
        curop=[]
        continue
    # ordinary comment line
    if incomment:
        curop.append(line)
        continue

    # ignore everything else


if methods:
    do_methods()

if mappings:
    do_mappings()

# remove double blank lines
op2=[]
for i in range(len(op)):
    if i+1<len(op) and len(op[i].strip())==0 and len(op[i+1].strip())==0:
        continue
    if len(op[i].strip())==0:
        op2.append("")
    else:
        op2.append(op[i].rstrip())
op=op2

open(sys.argv[2], "wt").write("\n".join(op)+"\n")