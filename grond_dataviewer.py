import Tkinter as tk       
from PIL import Image, ImageTk
import os
import sys
import sqlite3
import pyfits
from multiprocessing import Pool
import uuid
import re
import argparse

BASEDIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0,BASEDIR)
from lib import astImages

DEBUG = False

WIKI_URL = 'https://gamma-wiki.mpe.mpg.de/GROND/'
WIKI_PAGE = 'grond_dataQA'

DATABASE = os.path.join(BASEDIR,'dataviewer.db')
CACHE_DIR = os.path.join(BASEDIR,'cache')
FITS_REGEX = 'GROND_._OB_ana.fits'
IMAGE_ENGINE = astImages.saveBitmap
PLACEHOLDER_PNG = os.path.join(BASEDIR,'images/placeholder.png')
BANDS = 'grizJHK'

FLAGS = {
  0:  ('Guiding problems', 'flag_guiding'),
  1:  ('Focus problems', 'flag_focus'),
  2:  ('Readout noise problems', 'flag_roNoise'),
  3:  ('Unknown major problems', 'flag_unknownErr'),
}


def decodeIntFlag(val):
  #FLAGSET_LENGTH=64;x=67;z=[x & (2**n) for n in range(FLAGSET_LENGTH)]
  setFlags = [val & (2**n) for n in range(len(FLAGS))]
  return setFlags


def initdb():
  db = sqlite3.connect(DATABASE)
  SQL = '''
        CREATE TABLE Flags (id INTEGER PRIMARY KEY AUTOINCREMENT, target TEXT, viewed INTEGER, g, r, i, z, J, H, K);
        CREATE TABLE MissingImages (id INTEGER PRIMARY KEY AUTOINCREMENT, target TEXT, g, r, i, z, J, H, K);
        '''
  SQL = SQL.strip()
  if DEBUG:
    print "initdb: SQL:\n %s" % SQL
  db.executescript(SQL)
  db.commit()
  db.close()
  

class Application(tk.Frame):
  '''
  Creates the GROND data QA app.
  Loops (recursively) over the GROND_._OB_ana.fits images found in the CL specified
  path.
  Makes PNGs of the entire field, and presents them on a TKinter GUI. Saves the "flags"
  checkboxes to a sqlite3 database
  '''

  def __init__(self, args, master=None):
    self.args = args
    self.connectToDB()
    self.initTargets()
    self.initImages()
    tk.Frame.__init__(self, master)   
    self.grid()
    self.rowconfigure(0, weight=1)
    self.columnconfigure(0, weight=1)
    self.createWidgets()

  def initTargets(self):
    self.targets = []
    SQL = 'SELECT target FROM Flags'
    #if self.args.resume: #Not yet implemented
    #  SQL+= ' WHERE viewed==0'
    previous_targets = [i[0] for i in self.db.execute(SQL).fetchall()]
    if DEBUG:
      print "Walking directory structure to find GROND images. This may take a moment!"
    for path, dirs, files in os.walk(sys.argv[1]):
      for f in files:
        if re.search(FITS_REGEX,f):
          img = os.path.join(os.path.abspath(path),f)
          target = img[:re.search(FITS_REGEX,img).start()-2]
          if target not in self.targets:
            self.targets.append(target)
            if target not in previous_targets:
              SQL = '''
                    INSERT INTO Flags (target, viewed, %s) VALUES (%s, 0, %s); 
                    '''
              SQL = SQL.strip()
              SQL = SQL % (','.join([i for i in BANDS]), '"%s"' % target, ','.join(["0" for i in range(len(BANDS))]) )
              SQL+= '''
                    INSERT INTO MissingImages (target, %s) VALUES (%s, %s) 
                    '''     
              SQL = SQL.strip()
              SQL = SQL % (','.join([i for i in BANDS]), '"%s"' % target, ','.join(["0" for i in range(len(BANDS))]) )         
              if DEBUG:
                print "initTarget with SQL:\n%s" % SQL
              self.db.executescript(SQL)
              self.db.commit()
    self.current_target = self.targets[0]

  def initImages(self):
    '''
    Finds all GROND_._OB_ana.fits files in the CL specified directory
    Gives these images to the (async) process that creates the PNGs 
    '''
    pool = Pool(processes=4) 
    self.cache={}
    fitsimages = []
    missingimages = []
    for target in self.targets:
      for band in BANDS:
        img = os.path.join(target,'%s/GROND_%s_OB_ana.fits' % (band,band))
        if os.path.isfile(img):
          fitsimages.append(img)
        else:
          missingimages.append( (target,band) )
    for image in fitsimages:
      if IMAGE_ENGINE==astImages.saveBitmap:
       d = pyfits.open(image)[0].data
       fname = os.path.join(CACHE_DIR,'%s.png' % uuid.uuid4())
       #saveBitmap(outputFileName, imageData, cutLevels, size, colorMapName)
       #cutLevels=["smart", 99.5],size=300,colorMapName='gray'
       args = [fname,image,d,["smart", 99.5],300,'gray_r']
      #if IMAGE_ENGINE==lib.ds9: #Not yet implemented
      #  args = []
      if DEBUG:
        print "Running asnyc job with args=%s" % args
      loadvalue = float(fitsimages.index(image))/len(fitsimages)*100.0
      if not round(loadvalue) % 10:
        print "Loading: %0.1f%%" % (loadvalue)
      pool.apply_async(IMAGE_ENGINE,args,callback=self.updateCache)
    
    SQL = ''
    for target,band in missingimages:
      SQL += '''
            UPDATE MissingImages SET %s=1 WHERE target="%s";
            '''
      SQL = SQL.strip()
      SQL = SQL % (band,target)
    self.db.executescript(SQL)


  def updateCache(self,*args):
    '''
    Callback function that is called whenever an async task completes.
    Updates the internal cache with {FITS_path:PNG_path}
    '''
    image = args[0][0]
    fname = args[0][1]
    self.cache[image]=fname

  def connectToDB(self):
    if not os.path.isfile(DATABASE):
      initdb()
    self.db = sqlite3.connect(DATABASE)

  def getImagesFromCache(self):
    '''
    Looks into the internal cache for PNGs. If not there, returns a placeholder image
    '''
    L = []
    for band in BANDS:
      ct = self.current_target
      ci = os.path.join(ct,'%s/GROND_%s_OB_ana.fits' % (band,band))
      if ci in self.cache.keys():
        L.append(self.cache[ci])
      else:
        L.append(PLACEHOLDER_PNG)
    return L #List of PNG paths  
      

  def printPosition(self,widget):
    '''
    Print the TKinter grid position (debug purposes only)
    '''
    grid_info = widget.grid_info()
    print "row:", grid_info["row"], "column:", grid_info["column"] 

  def refresh(self):
    self.clear()
    self.createWidgets()

  def clear(self):
    [i.grid_forget() for i in self.imlabels]
    [b.grid_forget() for b in self.buttons]
    [c.grid_forget() for c in self.checkboxes]
    [l.grid_forget() for l in self.labels]
    [f.grid_forget() for f in self.frames]

  def save(self):
    '''
    Saves current info into the database
    '''
    
    SQL = '''  UPDATE Flags SET viewed=1 WHERE target=="%s"; ''' % self.current_target
    SQL = SQL.strip()
    for band in BANDS:
      value = 0
      for k,v in self.flags[band].iteritems():
        value += v.get()*2**k
      SQL+='UPDATE Flags SET %s=%s WHERE target=="%s";' % (band,value,self.current_target)
    if DEBUG:
      print "save with SQL:\n%s" % SQL
    self.db.executescript(SQL)
    self.db.commit()
      

  def quit(self):
    self.save()
    if DEBUG:
      print "Cleanup: Removing all PNGs in %s" % CACHE_DIR
    os.system('rm %s/*png' % CACHE_DIR)
    #super(Application,self).quit() #tk.Frame is old-style class, super() won't work!
    tk.Frame.quit(self)
    if self.args.user:
      uploadToWiki(self.args,self.db)

  def jump_to(self,lb):
    self.save()
    selection=lb.curselection()
    target = lb.get(selection[0])
    self.current_target = target
    self.clear()
    self.createWidgets()

  def next(self):
    self.save()
    try:
      self.current_target = self.targets[self.targets.index(self.current_target)+1]
    except IndexError:
      print "\n---> Done.\n"
      self.quit()   
    self.clear()
    self.createWidgets()


  def getFlagVal(self,band,flagIndex):
    SQL = '''
          SELECT %s FROM Flags WHERE target="%s"
          '''
    SQL=SQL.strip()
    SQL = SQL % (band,self.current_target)
    if DEBUG:
      print "Querying for set flags with SQL:\n%s" % SQL
    intFlag = self.db.execute(SQL).fetchall()[0][0]
    L = decodeIntFlag(intFlag)
    if not L[flagIndex]:
      return "0"
    return "1" #TK expects string booleans


  def createWidgets(self):
    self.imlabels = []
    col,row = 0,0
    colspan = len(FLAGS)*2
    rowspan = colspan
    for image in self.getImagesFromCache():
      photo = ImageTk.PhotoImage(Image.open(image))
      imlabel = tk.Label(self,image=photo)
      imlabel.image = photo # keep a reference!
      imlabel.grid(column=col,row=row,columnspan=colspan,rowspan=rowspan,sticky=tk.W+tk.E+tk.S+tk.N)
      col += 1*colspan
      if col > 2*colspan:
        row += 1*rowspan
        col = 0
      self.imlabels.append(imlabel)

    self.buttons = []
    self.checkboxes = []
    self.labels = []
    self.frames = []
    startcol = 0
    startrow = row+1*rowspan
    col,row = startcol, startrow
    colspan = len(FLAGS)
    rowspan = 1
    self.flags = {}
    for band in BANDS:
      self.flags[band] = {}
      l = tk.Label(self,text=band)
      l.grid(column=col,row=row)
      self.labels.append(l)
      for flagIndex,(flagTxt,flagDBname) in FLAGS.iteritems():
        row+=1*rowspan
        self.flags[band][flagIndex] = tk.IntVar()
        self.flags[band][flagIndex].set(self.getFlagVal(band,flagIndex))
        c = tk.Checkbutton(self,text=flagTxt,variable=self.flags[band][flagIndex])
        c.grid(column=col,row=row,columnspan=colspan,rowspan=rowspan,sticky=tk.W)
        self.checkboxes.append(c)
      col+=1*colspan
      row = startrow

    
    b = tk.Button(self, text='Save and Quit', command=self.quit)
    b.grid(column=100,row=0)        
    self.buttons.append(b)

    b = tk.Button(self, text="Save and continue",command=self.next)
    b.grid(column=100,row=100)
    self.buttons.append(b)
    
    b = tk.Button(self, text="Refresh page",command=self.refresh)
    b.grid(column=0,row=100)
    self.buttons.append(b)

    text = "%s (%s/%s)" % (self.current_target,self.targets.index(self.current_target)+1,len(self.targets))
    l = tk.Label(self,text=text)
    l.grid(column=50,row=100)
    self.labels.append(l)

    SQL = 'SELECT viewed FROM Flags WHERE target=="%s"' % self.current_target
    result = self.db.execute(SQL).fetchall()[0][0]
    if result:
      text = "This target has been viewed at least once before"
      l = tk.Label(self,text=text,fg="blue")
      l.grid(column=1,row=100,columnspan=5,sticky=tk.W)
      self.labels.append(l)

    f = tk.Frame(self,borderwidth=5, relief="sunken")  
    f.grid(column=100,row=1,sticky=tk.W,rowspan=100)
    self.frames.append(f)
    sb = tk.Scrollbar(f)
    sb.pack(side=tk.RIGHT, fill=tk.Y)
    lb = tk.Listbox(f,height=25)
    lb.pack(side=tk.LEFT)

    for t in self.targets:
      lb.insert(tk.END, t)
      SQL = '''
            SELECT viewed FROM Flags where target="%s"
            '''
      SQL = SQL.strip()
      SQL = SQL % t
      if self.db.execute(SQL).fetchall()[0][0]:
        lb.itemconfig(self.targets.index(t), bg='blue', fg='white')
    lb.config(yscrollcommand=sb.set)
    sb.config(command=lb.yview)
  
    b = tk.Button(f,text="Go",command=lambda: self.jump_to(lb))
    b.pack()

    if DEBUG:
      print "Images:"
      [self.printPosition(i) for i in self.imlabels]
      print "Buttons:"
      [self.printPosition(b) for b in self.buttons]
      print "Frames:"
      [self.printPosition(f) for f in self.frames]
      print "Checkboxes:"
      [self.printPosition(c) for c in self.checkboxes]


def uploadToWiki(args,db):
  from lib import wikipage
  print "Attempting to upload to [%s%s]" % (WIKI_URL,WIKI_PAGE)
  wikibot = wikipage.WikiPage(wiki_url=WIKI_URL,pagename=WIKI_PAGE,username=args.user,password=args.passwd)
  wikibot.login()
  wikibot.open() 
  
  table = []
  header = '''
                || \'\'\'Path\'\'\' || \'\'\'Viewed?\'\'\' || \'\'\'g\'\'\' || \'\'\'r\'\'\' || \'\'\'i\'\'\' || \'\'\'z\'\'\' || \'\'\'J\'\'\' || \'\'\'H\'\'\' || \'\'\'K\'\'\' || \'\'\'Missing images?\'\'\' ||
           '''
  table.append(header.strip())
  tablerow = '''
                ||%s||%s||%s||%s||%s||%s||%s||%s||%s||%s||
             '''
  tablerow = tablerow.strip()

  results = db.execute('SELECT * from Flags').fetchall()
  for row in results:
    missingQuery = db.execute('SELECT g,r,i,z,J,H,K from MissingImages WHERE target="%s"' % row[1]).fetchall()[0]
    print missingQuery
    mapping = dict([(BANDS.index(b)+1,b) for b in BANDS])
    missing = ''
    #row = [i if len(str(i)) <= 30 else i[-30:] for i in row]
    row = list(row)[1:]
    if row[1]:
      row[1] = '<bgcolor=\"#003CFF\"> Yes '
    for i in range(7):
      if missingQuery[i]:
        missing+=mapping[i]      
      if row[i+2]:
        row[i+2] = '<bgcolor=\"#FF0000\"> %s ' % row[i+2]
    row.append(missing)    
    data = tablerow % tuple(row)
    table.append(data)

  wikibot.linelist = table
  wikibot.save()
  wikibot.logout()




if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument('PATH',nargs=1)
  parser.add_argument('-u','--user',nargs=1,required=False,dest="user")
  parser.add_argument('-p','--password',nargs=1,required=False,dest="passwd")
  args = parser.parse_args()
  if DEBUG:
    print args
  app = Application(args)                       
  app.master.title('GROND data QA')    
  app.mainloop()          
                  
