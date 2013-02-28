'''
Created on Feb 5, 2013

@author: lukovnikov
'''
import re
from operator import attrgetter
from lucene import *
from dbwikipagelinks.wikipagelinks import PageLinkGetter, RedirectGetter

class BabelNet():
    def __init__(self, indicesdir="/home/denis/Soft/babelnet-api-1.1.0/indices/"):
        lexiconindex = indicesdir + "lexicon"
        graphindex = indicesdir + "graph"
        glossindex = indicesdir + "gloss"
        dictindex = indicesdir + "dict"
        lexicondir = SimpleFSDirectory(File(lexiconindex))
        graphdir = SimpleFSDirectory(File(graphindex))
        glossdir = SimpleFSDirectory(File(glossindex))
        dictdir = SimpleFSDirectory(File(dictindex))
        self.dictionary = IndexSearcher(dictdir, True)
        self.lexicon = IndexSearcher(lexicondir, True)
        self.graph = IndexSearcher(graphdir, True)
        self.gloss = IndexSearcher(glossdir, True)
        self.maxnum = 100
        
    def searchMeanings(self, word, language = "EN", separator = ":", pos='n', partial=False):
        word = re.sub(" ","_",word)
        word = word.lower()
        q = BooleanQuery()
        q.setMinimumNumberShouldMatch(1)
        langword = language + separator + word
        q.add(BooleanClause(TermQuery(Term("LANGUAGE_LEMMA", langword)),
                            BooleanClause.Occur.SHOULD))
        if pos:
            q.add(BooleanClause(TermQuery(Term("POS",pos)),
                            BooleanClause.Occur.MUST))
        #query built
        docs = self.dictionary.search(q, self.maxnum)
        meanings = []
        for scoreDoc in docs.scoreDocs:
            doc = self.dictionary.doc(scoreDoc.doc)
            conc = BabelConcept(doc)
            conc.score = scoreDoc.score * len(self.getSuccessors(conc.id))
            meanings.append(conc)
        if partial:
            qp = BooleanQuery()
            qp.setMinimumNumberShouldMatch(1)
            qp.add(BooleanClause(WildcardQuery(Term("LANGUAGE_LEMMA", language+separator+"*"+word+"*")),BooleanClause.Occur.SHOULD))
            qp.add(BooleanClause(TermQuery(Term("POS", pos)), BooleanClause.Occur.MUST))
            pdocs = self.dictionary.search(qp, self.maxnum)
            for scoreDoc in pdocs.scoreDocs:
                doc = self.dictionary.doc(scoreDoc.doc)
                conc = BabelConcept(doc)
                conc.score = scoreDoc.score * len(self.getSuccessors(conc.id))
                meanings.append(conc)
        return meanings
    
    def getConceptById(self, id):
        if id == None:
            return None
        q = TermQuery(Term("ID",id))
        result = self.dictionary.search(q, 1)
        if len(result.scoreDocs)>0:
            doc = result.scoreDocs[0]
            return BabelConcept(self.dictionary.doc(doc.doc))
        else:
            return None
    
    def getIdByConcept(self, url):
        dbpediaprefix = "http://dbpedia.org/resource/"
        url = url[len(dbpediaprefix):]
        q = TermQuery(Term("LEMMA", url))
        result = self.dictionary.search(q,1)
        if len(result.scoreDocs)>0:
            doc = result.scoreDocs[0]
            return self.dictionary.doc(doc.doc).get("ID")
        else:
            return None
        
    def getConceptByUrl(self, url):
        return self.getConceptById(self.getIdByConcept(url))
    
    def getSuccessors(self, cid):
        q = TermQuery(Term("ID", cid))
        docs = self.graph.search(q, 1)
        doc = self.graph.doc(docs.scoreDocs[0].doc)
        successors = doc.get("RELATION")
        succs = successors.split("\t")
        succacc = []
        for s in succs:
            m = re.search("(?P<lan>[A-Z]{2})_r_(?P<id>bn:\d+[a-z])_(?P<first>0.\d+)_(?P<second>0.\d+)\Z", s)
            if m:
                succacc.append((m.group("id"), m.group("lan"), float(m.group("first")), float(m.group("second"))))
        return succacc
    
    #WATCH OUT !!!       THE FOLLOWING METHOD DOESN'T REALLY GET THE BABELNET PREDECESSORS
    #                    IT GETS JUST WIKIPEDIA PAGES INCOMING INTO THE ARTICLE INSTEAD !!!
    def getPredecessors(self, cid):
        conc = self.getConceptById(cid)
        dbprefix= "http://dbpedia.org/resource/"
        if conc.onDBpedia:
            inlinks = PageLinkGetter.getInlinksUrl(conc.url)
            acc = []
            for i in inlinks:
                ide = self.getIdByConcept(i)
                if ide == None:
                    url = RedirectGetter.getRedirect(i)
                    if url != None:
                        ide = self.getIdByConcept(url)
                if ide != None:     
                    ap = (ide, "NN", 0.0, 0.0)
                    acc.append(ap)
            return acc
        else:
            return []
        #=======================================================================
        # q = WildcardQuery(Term("RELATION","*"+cid+"*"))
        # print cid
        # docs = self.graph.search(q,50)
        # acc = []
        # for doc in docs.scoreDocs:
        #    doc = self.graph.doc(doc.doc)
        #    acc.append(doc.get("ID"))
        # return acc
        #=======================================================================
            
class BabelConcept():
    def __init__(self, doc):
        self.lemmas = []
        fields = doc.getFields()
        i = 0
        while i < fields.size():
            field = fields.get(i)
            if field.name()=="LANGUAGE_LEMMA":
                self.addField("lemmas", Lemma(fields,i))
                i = i+7
            else:
                self.addField(field.name().lower(), field.stringValue())
                i = i+1
        self.id = doc.get("ID")
        self.pos = doc.get("POS")
        self.source = doc.get("SOURCE")
        self.wordnet_offset = doc.get("WORDNET_OFFSET")
        
    def addField(self, name, value):
        if hasattr(self, name):
            val = getattr(self, name)
            if isinstance(val, list):
                val.append(value)
            else:
                newval = [val, value]
                setattr(self, name, newval)
        else:
            setattr(self, name, value)
    
    def __str__(self):
        return self.id
    
    def __repr__(self):
        return self.cid
    
    @property
    def cid(self):
        return self.main_sense if self.url==None else self.url
    
    @property
    def onDBpedia(self):
        return self.url!=None
    
    @property
    def url(self):
        return self.dbpediaurl
    
    @property
    def dbpediaurl(self):
        main = self.maindbpediaurl
        urls = []
        if not main:
            for lem in self.lemmas:
                if lem.source=="WIKI" and lem.language=="EN":
                    urls.append(BabelConcept.dbpedify(lem.lemma))
        else:
            return main
        if len(urls)>0:
            return urls[0]
        else:
            return None
    
    @property
    def maindbpediaurl(self):
        if self.main_sense.startswith("WIKI"):
            url = re.sub("WIKI\w*:\w{2}:","",self.main_sense)
            url = BabelConcept.dbpedify(url)
            return url
        else:
            return None
        
    @classmethod
    def dbpedify(cls, lemma):
        return "http://dbpedia.org/resource/" + lemma
            
class Lemma():
    def __init__(self, fields, i):
        if fields.get(i+1).name()=="LEMMA":
            self.lemma = fields.get(i+1).stringValue()
        if fields.get(i+5).name()=="LEMMA_SOURCE":
            self.source = fields.get(i+5).stringValue()
        if fields.get(i+3).name()=="LEMMA_LANGUAGE":
            self.language = fields.get(i+3).stringValue()
        if fields.get(i+4).name()=="LEMMA_WEIGHT":
            self.weight = fields.get(i+4).stringValue()
        if fields.get(i+6).name()=="LEMMA_SENSEKEY":
            self.sensekey = fields.get(i+6).stringValue()

if __name__=="__main__":
    initVM()
    bn = BabelNet()
    meanings = bn.searchMeanings("emma stone")
    meanings = sorted(meanings, key=attrgetter("score"),reverse=True)
    print bn.getIdByConcept("http://dbpedia.org/resource/Cheese_(album)")
    for m in meanings:
        if m.onDBpedia:
            print m.cid
            #print bn.getPredecessors(m.id)
            for id in bn.getSuccessors(m.id):
                conc = bn.getConceptById(id[0])
                print "\t" +str(id) + "\t "+ conc.cid
            print "Predecessors:"
            for id in bn.getPredecessors(m.id):
                print str(id)
        #print bn.getConceptById(id).main_sense